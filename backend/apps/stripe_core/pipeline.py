"""Run full setup pipeline with live events."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.projects.models import Project
from apps.projects.scanner import ProjectScanner
from apps.vault.models import get_secret, hydrate_project_vault, vault_health

from .codegen import generate_all, write_codegen_files
from .events import EventEmitter, PipelineEvent, emit
from .provision import ProvisionConfig, load_manifest, provision_catalog
from .hub_keys import HUB_SLUG, pull_stripe_keys_for_user, resolve_production_app_url, resolve_web_app_url
from .portfolio_catalog import is_stripe_exempt_slug
from .readiness import readiness_label, run_readiness_checks, score_readiness
from .stripe_config import provision_config_from_stripe_file, write_stripe_config
from .verify import KeyCheck, VerificationResult, verify_stripe_keys

MAX_STORED_ARTIFACT_BYTES = 3 * 1024 * 1024


@dataclass
class PipelineOptions:
    provision: bool = True
    generate: bool = True
    sync_env: bool = False
    force: bool = False
    include_readiness: bool = True
    app_url: str = "http://localhost:8000"


@dataclass
class PipelineResult:
    verification: dict[str, Any]
    provision: dict[str, Any] | None = None
    files_written: list[str] | None = None
    generated_files: dict[str, str] | None = None
    readiness_score: int | None = None
    readiness_checks: list[dict[str, Any]] | None = None


def _project_root(project: Project) -> Path:
    from apps.stripe_core.portfolio_workspace import ensure_project_workspace

    ensure_project_workspace(project)
    if not project.local_path:
        raise ValueError(
            "Set local_path to your real app folder (e.g. C:\\Software Projects\\YourApp) before running setup."
        )
    root = Path(project.local_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(
            f"Project folder not found: {root}. Clone the repo there manually, then set local_path in Settings."
        )
    return root


def _webhook_path(framework: str, scan_data: dict | None = None) -> str:
    if scan_data:
        for key in ("webhookPath", "webhook_path"):
            path = scan_data.get(key)
            if path:
                return str(path)
    if framework in ("nextjs", "remix", "nuxt", "sveltekit"):
        return "/api/stripe/webhook"
    if framework == "django":
        return "/webhooks/stripe/"
    return "/stripe/webhook"


def _sync_env(project_root: Path, project: Project) -> None:
    updates: dict[str, str] = {}
    for key in (
        "STRIPE_SECRET_KEY",
        "STRIPE_PUBLISHABLE_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
        "DATABASE_URL",
    ):
        value = get_secret(project, key)
        if value:
            updates[key] = value
    if not updates:
        return
    env_path = project_root / ".env.local"
    existing = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
    out_lines: list[str] = []
    written_keys: set[str] = set()
    for line in existing.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates:
            out_lines.append(f"{key}={updates[key]}")
            written_keys.add(key)
        else:
            out_lines.append(line)
    for key, value in updates.items():
        if key not in written_keys:
            out_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(out_lines).rstrip() + "\n", encoding="utf-8")


def _run_codegen(
    project: Project,
    project_root: Path,
    *,
    app_url: str,
    force: bool,
    on_event: EventEmitter | None,
) -> tuple[list[str], dict[str, str]]:
    scan_data = project.scan_data or {}
    next_router = scan_data.get("nextRouter")
    manifest = load_manifest(project_root)

    files = generate_all(
        project.framework,
        manifest,
        app_url=app_url,
        next_router=next_router,
    )
    results = write_codegen_files(project, project_root, files, force=force)

    written = [r.path for r in results if r.action in ("created", "updated")]
    for result in results:
        if result.action == "skipped":
            emit(
                on_event,
                PipelineEvent("generate.file", "detail", f"Skipped (exists): {result.path}", detail=True),
            )
        else:
            emit(on_event, PipelineEvent("generate.file", "detail", result.path, detail=True))

    total_bytes = sum(len(c.encode("utf-8")) for c in files.values())
    stored = files if total_bytes <= MAX_STORED_ARTIFACT_BYTES else {path: "" for path in files}
    return written, stored


def _readiness_score(project: Project, project_root: Path, app_url: str) -> tuple[int, list[dict[str, Any]]]:
    checks = run_readiness_checks(project, project_root, production_url=app_url)
    score = score_readiness(checks)
    return score, [c.to_dict() for c in checks]


def run_pipeline(
    project: Project,
    on_event: EventEmitter | None = None,
    opts: PipelineOptions | None = None,
) -> PipelineResult:
    options = opts or PipelineOptions()
    emit(on_event, PipelineEvent("run.started", "running", "Starting full setup…"))

    from apps.deploy.platform_bootstrap import prepare_project_automation

    prep = prepare_project_automation(project, user=project.owner)
    for item in prep.get("steps") or []:
        emit(on_event, PipelineEvent(f"automation.{item['step']}", "ok", item["detail"]))

    project_root: Path | None = None
    try:
        project_root = _project_root(project)
    except (ValueError, FileNotFoundError) as exc:
        emit(on_event, PipelineEvent("vault.hydrate", "warn", str(exc)))

    if project_root:
        emit(
            on_event,
            PipelineEvent("vault.hydrate", "running", "Loading secrets from local vault store…"),
        )
        try:
            imported = hydrate_project_vault(project)
            if imported:
                emit(
                    on_event,
                    PipelineEvent(
                        "vault.hydrate",
                        "ok",
                        f"Restored {len(imported)} key(s) from ~/.stripe-installer or project env",
                    ),
                )
        except Exception as exc:
            emit(on_event, PipelineEvent("vault.hydrate", "warn", str(exc)))

    if project.slug != HUB_SLUG:
        copied = pull_stripe_keys_for_user(project, project.owner)
        if copied:
            emit(
                on_event,
                PipelineEvent(
                    "vault.hydrate",
                    "ok",
                    f"Pulled {len(copied)} Stripe key(s) from Automation Center hub",
                ),
            )

    stripe_exempt = is_stripe_exempt_slug(project.slug)
    secret = get_secret(project, "STRIPE_SECRET_KEY")
    publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")

    emit(on_event, PipelineEvent("verify.keys", "running", "Verifying API keys…"))
    if stripe_exempt:
        verification = VerificationResult(
            secret_key=KeyCheck(True, "unknown", "Portfolio exempt — Stripe keys not required"),
            publishable_key=KeyCheck(True, "unknown", "Portfolio exempt — Stripe keys not required"),
        )
        emit(
            on_event,
            PipelineEvent("verify.keys", "ok", "Portfolio exempt — skipping Stripe key verification"),
        )
    else:
        verification = verify_stripe_keys(secret, publishable)
        if not verification.secret_key.valid:
            health = vault_health(project)
            if health["unreadableCount"]:
                msg = (
                    f"{verification.secret_key.message} "
                    "(Restore keys via the vault UI, Import from .env, or save them once — "
                    "they persist under ~/.stripe-installer/projects/.)"
                )
            else:
                msg = verification.secret_key.message
            emit(on_event, PipelineEvent("verify.keys", "failed", msg))
            raise ValueError(msg)

        mode_label = "live mode" if verification.secret_key.mode == "live" else "test mode"
        emit(on_event, PipelineEvent("verify.keys", "ok", f"API keys verified ({mode_label})"))

    if not project_root:
        project_root = _project_root(project)

    if project.framework == "unknown" or not project.scan_data:
        from apps.stripe_core.portfolio_workspace import resolve_scan_root

        scan = ProjectScanner(resolve_scan_root(project_root)).scan()
        project.framework = scan.framework
        project.language = scan.language
        project.scan_data = scan.to_dict()
        project.save(update_fields=["framework", "language", "scan_data", "updated_at"])

    webhook_path = _webhook_path(project.framework, project.scan_data)
    prod_url = resolve_web_app_url(project) or resolve_production_app_url(project)
    app_url = (prod_url or options.app_url).rstrip("/")
    provision_data = None
    files_written: list[str] = []
    generated_files: dict[str, str] | None = None

    if options.provision and secret:
        stripe_opts = provision_config_from_stripe_file(
            project_root,
            app_url=app_url,
            webhook_path=webhook_path,
        )
        if not (project_root / "stripe.config.json").is_file():
            write_stripe_config(
                project_root,
                {
                    "appUrl": stripe_opts["app_url"],
                    "provision": {
                        "reuseExisting": stripe_opts["reuse_existing"],
                        "createWebhook": stripe_opts["create_webhook"],
                        "createPortal": stripe_opts["create_portal"],
                    },
                },
            )
        prov = provision_catalog(
            secret,
            project_root,
            project=project,
            account_id=verification.account_id,
            config=ProvisionConfig(
                tiers=stripe_opts["tiers"],
                webhook_url=stripe_opts["webhook_url"],
                billing_portal_return_url=stripe_opts["billing_portal_return_url"],
                app_url=stripe_opts["app_url"],
                reuse_existing=stripe_opts["reuse_existing"],
                create_webhook=stripe_opts["create_webhook"],
                create_portal=stripe_opts["create_portal"],
            ),
            on_event=on_event,
        )
        provision_data = {
            "products": prov.products,
            "prices": prov.prices,
            "webhookUrl": prov.webhook_endpoint.get("url") if prov.webhook_endpoint else None,
            "billingPortalConfig": prov.billing_portal_config,
            "webhookSecretStored": prov.webhook_secret_stored,
            "warnings": prov.warnings,
        }
        if prov.webhook_secret_stored:
            from apps.deploy.env_push import try_auto_push_railway_stripe_env

            env_push = try_auto_push_railway_stripe_env(project)
            if env_push is not None:
                provision_data["envPush"] = env_push
                if env_push.get("ok"):
                    emit(
                        on_event,
                        PipelineEvent(
                            "deploy.railway-env",
                            "ok",
                            env_push.get("message", "Railway env vars updated"),
                        ),
                    )
                elif not env_push.get("skipped"):
                    emit(
                        on_event,
                        PipelineEvent(
                            "deploy.railway-env",
                            "failed",
                            env_push.get("message", "Railway env push failed"),
                        ),
                    )

    if options.generate:
        if stripe_exempt:
            emit(
                on_event,
                PipelineEvent(
                    "generate.code",
                    "ok",
                    "Portfolio exempt — skipping Stripe codegen",
                ),
            )
        else:
            emit(on_event, PipelineEvent("generate.code", "running", "Generating code…"))
            files_written, generated_files = _run_codegen(
                project,
                project_root,
                app_url=app_url,
                force=options.force,
                on_event=on_event,
            )
            count = len(files_written)
            emit(
                on_event,
                PipelineEvent(
                    "generate.code",
                    "ok",
                    f"Code generated ({count} file{'s' if count != 1 else ''})",
                ),
            )

    if options.sync_env:
        emit(on_event, PipelineEvent("sync.env", "running", "Syncing .env.local…"))
        _sync_env(project_root, project)
        emit(on_event, PipelineEvent("sync.env", "ok", "Environment synced"))

    readiness_score = None
    readiness_checks = None
    if options.include_readiness:
        emit(on_event, PipelineEvent("readiness", "running", "Running readiness checks…"))
        readiness_score, readiness_checks = _readiness_score(project, project_root, app_url)
        label = readiness_label(readiness_score)
        emit(
            on_event,
            PipelineEvent("readiness", "ok", f"Readiness score: {readiness_score}/100 — {label}"),
        )

    done_msg = (
        f"Done — Readiness Score: {readiness_score}/100"
        if readiness_score is not None
        else "Done — setup complete"
    )
    emit(on_event, PipelineEvent("run.completed", "ok", done_msg, score=readiness_score))

    return PipelineResult(
        verification=verification.to_public_dict(),
        provision=provision_data,
        files_written=files_written or None,
        generated_files=generated_files,
        readiness_score=readiness_score,
        readiness_checks=readiness_checks,
    )
