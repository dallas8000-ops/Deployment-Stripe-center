"""Auto-fix actions — port of repair.ts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from apps.projects.models import Project
from apps.stripe_installer.codegen import generate_all, write_project_files
from apps.diagnostics.diagnostics import DiagnosticReport, run_diagnostics
from apps.stripe_installer.pipeline import _sync_env, _webhook_path
from apps.stripe_installer.provision import ProvisionConfig, provision_catalog
from apps.stripe_installer.verify import verify_stripe_keys
from apps.vault.models import get_secret, set_secret

DEFAULT_CONFIG = {
    "appUrl": "http://localhost:8000",
    "tiers": [
        {"name": "Starter", "amount": 900, "currency": "usd", "interval": "month", "trialDays": 14},
        {"name": "Pro", "amount": 2900, "currency": "usd", "interval": "month", "trialDays": 14},
    ],
}


@dataclass
class RepairResult:
    action: str
    success: bool
    message: str
    files: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _project_root(project: Project) -> Path:
    if not project.local_path:
        raise ValueError("Project local_path is required")
    root = Path(project.local_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project path not found: {root}")
    return root


def _fix_gitignore(project_root: Path) -> RepairResult:
    path = project_root / ".gitignore"
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    additions = [".env", ".env.local", ".env.*.local", ".stripe-installer/"]
    existing = {line.strip() for line in content.splitlines() if line.strip()}
    added = [a for a in additions if a not in existing and a not in content]
    if not added:
        return RepairResult("fix-gitignore", True, ".gitignore already configured")
    block = "\n# Stripe Installer\n" + "\n".join(added) + "\n"
    path.write_text(content.rstrip() + block, encoding="utf-8")
    return RepairResult("fix-gitignore", True, f"Added {', '.join(added)} to .gitignore")


def _create_stripe_config(project_root: Path) -> RepairResult:
    dest = project_root / "stripe.config.json"
    if dest.is_file():
        return RepairResult("create-stripe-config", True, "stripe.config.json already exists")
    import json

    dest.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    return RepairResult("create-stripe-config", True, "Created stripe.config.json")


def _sync_public_key(project: Project) -> RepairResult:
    pk = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
    if not pk:
        return RepairResult("sync-public-key", False, "STRIPE_PUBLISHABLE_KEY not in vault")
    set_secret(project, "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", pk)
    return RepairResult("sync-public-key", True, "Synced NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY")


def _generate_infra(project: Project, project_root: Path, force: bool, app_url: str) -> RepairResult:
    from apps.deploy.infra import generate_and_write_infra

    _, results = generate_and_write_infra(project, force=force, prod_url=app_url)
    created = [r.path for r in results if r.action != "skipped"]
    if not created:
        return RepairResult("generate-infra", True, "All infra files already exist")
    return RepairResult("generate-infra", True, f"Generated {len(created)} deploy file(s)", files=created)


def _generate_files(project: Project, project_root: Path, force: bool) -> RepairResult:
    from apps.stripe_installer.provision import load_manifest

    manifest = load_manifest(project_root)
    files = generate_all(project.framework, manifest)
    results = write_project_files(project_root, files, force=force)
    created = [r.path for r in results if r.action != "skipped"]
    if not created:
        return RepairResult("generate-files", True, "All integration files already exist")
    return RepairResult("generate-files", True, f"Generated {len(created)} file(s)", files=created)


def _provision_stripe(project: Project, project_root: Path, app_url: str) -> RepairResult:
    secret = get_secret(project, "STRIPE_SECRET_KEY")
    if not secret:
        return RepairResult("provision-stripe", False, "STRIPE_SECRET_KEY not in vault")
    verification = verify_stripe_keys(secret, get_secret(project, "STRIPE_PUBLISHABLE_KEY"))
    webhook_path = _webhook_path(project.framework)
    result = provision_catalog(
        secret,
        project_root,
        project=project,
        account_id=verification.account_id,
        config=ProvisionConfig(
            webhook_url=f"{app_url.rstrip('/')}{webhook_path}",
            billing_portal_return_url=f"{app_url.rstrip('/')}/stripe/account/",
            app_url=app_url,
        ),
    )
    return RepairResult(
        "provision-stripe",
        True,
        f"Provisioned {len(result.prices)} price(s), webhook {'registered' if result.webhook_endpoint else 'skipped'}",
    )


def run_repair_action(
    project: Project,
    action: str,
    *,
    force: bool = False,
    app_url: str = "http://localhost:8000",
) -> RepairResult:
    root = _project_root(project)
    if action == "fix-gitignore":
        return _fix_gitignore(root)
    if action == "create-stripe-config":
        return _create_stripe_config(root)
    if action == "sync-public-key":
        return _sync_public_key(project)
    if action == "sync-env":
        _sync_env(root, project)
        return RepairResult("sync-env", True, "Synced vault to .env.local")
    if action == "generate-files":
        return _generate_files(project, root, force)
    if action == "generate-infra":
        return _generate_infra(project, root, force, app_url)
    if action == "provision-stripe":
        return _provision_stripe(project, root, app_url)
    return RepairResult(action, False, f"Unknown action: {action}")


def run_auto_fix(
    project: Project,
    *,
    issue_ids: list[str] | None = None,
    force: bool = False,
    app_url: str = "http://localhost:8000",
) -> tuple[list[RepairResult], DiagnosticReport]:
    root = _project_root(project)
    report = run_diagnostics(project, root)
    targets = report.issues
    if issue_ids:
        id_set = set(issue_ids)
        targets = [i for i in targets if i.id in id_set]

    actions: list[str] = []
    for issue in targets:
        if issue.auto_fixable and issue.fix_action and issue.fix_action not in actions:
            actions.append(issue.fix_action)

    repairs: list[RepairResult] = []
    for action in actions:
        try:
            repairs.append(run_repair_action(project, action, force=force, app_url=app_url))
        except Exception as exc:
            repairs.append(RepairResult(action, False, str(exc)))

    new_report = run_diagnostics(project, root)
    return repairs, new_report
