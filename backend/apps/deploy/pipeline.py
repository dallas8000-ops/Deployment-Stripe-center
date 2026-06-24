"""Unified deploy pipeline — Stripe setup + infra + postgres + manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.projects.models import Project
from apps.stripe_core.events import EventEmitter, PipelineEvent, emit
from apps.stripe_core.pipeline import PipelineOptions, PipelineResult, run_pipeline
from apps.stripe_core.portfolio_catalog import catalog_by_slug
from apps.stripe_core.readiness import readiness_label
from apps.stripe_core.portfolio_catalog import is_stripe_exempt_slug

from .config import config_from_project, sync_project_from_config, write_deploy_config
from .infra import generate_and_write_infra
from .platform import detect_deploy_platform, health_check_path, platform_deploy_command
from .platform_push import push_to_platform
from .postgres import get_database_url, get_production_url, test_postgres_connection
from .provision import provision_postgres


def format_readiness_report(checks: list[dict[str, Any]], score: int) -> str:
    lines = ["# Production Readiness Report", "", f"Score: {score}/100", ""]
    categories = sorted({c.get("category", "general") for c in checks})
    for cat in categories:
        lines.append(f"## {cat.capitalize()}")
        for check in [c for c in checks if c.get("category") == cat]:
            status = check.get("status", "fail")
            icon = "✓" if status == "pass" else "!" if status == "warn" else "✗"
            lines.append(f"- [{icon}] **{check.get('name', '')}**: {check.get('message', '')}")
            if check.get("fix") and status != "pass":
                lines.append(f"  - Fix: {check['fix']}")
        lines.append("")
    return "\n".join(lines)


@dataclass
class DeployOptions:
    provision_stripe: bool = True
    generate_code: bool = True
    sync_env: bool = False
    force: bool = False
    include_infra: bool = True
    provision_postgres: bool = True
    include_readiness: bool = True
    push_platform: bool = False
    push_railway_env: bool = True
    app_url: str = "http://localhost:8000"
    postgres_provider: str | None = None


@dataclass
class DeployResult:
    pipeline: PipelineResult
    files_written: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    platform: str = "unknown"
    production_url: str = ""
    postgres_connected: bool | None = None
    push_result: dict[str, Any] | None = None
    env_push_result: dict[str, Any] | None = None
    manifest: dict[str, Any] = field(default_factory=dict)


def _project_root(project: Project) -> Path:
    from apps.stripe_core.portfolio_workspace import (
        ensure_project_workspace,
        sync_portfolio_scan_metadata,
    )

    ensure_project_workspace(project, clone_if_missing=True)
    sync_portfolio_scan_metadata(project)
    if not project.local_path:
        raise ValueError("Project local_path is required")
    root = Path(project.local_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project path not found: {root}")
    return root


def _write_text(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_deploy_pipeline(
    project: Project,
    on_event: EventEmitter | None = None,
    opts: DeployOptions | None = None,
) -> DeployResult:
    options = opts or DeployOptions()
    root = _project_root(project)
    deploy_cfg = config_from_project(project, root)
    prod_url = get_production_url(project, options.app_url)
    scan = project.scan_data or {}
    platform = (
        deploy_cfg.get("platform")
        if deploy_cfg.get("platform") not in (None, "", "unknown")
        else scan.get("deployPlatform") or detect_deploy_platform(root, project.framework)
    )
    postgres_provider = (
        options.postgres_provider
        or (deploy_cfg.get("postgres") or {}).get("provider")
        or "neon"
    )
    if postgres_provider == "unknown":
        postgres_provider = "neon"
    auto_provision = (deploy_cfg.get("postgres") or {}).get("autoProvision", True)

    emit(on_event, PipelineEvent("deploy.started", "running", "Starting full deploy pipeline…"))

    pipeline_result = run_pipeline(
        project,
        on_event=on_event,
        opts=PipelineOptions(
            provision=options.provision_stripe,
            generate=options.generate_code,
            sync_env=options.sync_env,
            force=options.force,
            include_readiness=options.include_readiness,
            app_url=prod_url,
        ),
    )

    all_written = list(pipeline_result.files_written or [])
    next_steps: list[str] = []

    if options.include_infra:
        emit(on_event, PipelineEvent("deploy.infra", "running", "Generating deploy infrastructure…"))
        _, infra_results = generate_and_write_infra(project, force=options.force, prod_url=prod_url)
        infra_paths = [r.path for r in infra_results if r.action != "skipped"]
        all_written.extend(infra_paths)
        emit(
            on_event,
            PipelineEvent(
                "deploy.infra",
                "ok",
                f"Infrastructure files ({len(infra_paths)} written)",
            ),
        )

    postgres_provisioned = None
    skip_stripe_schema = is_stripe_exempt_slug(project.slug)
    if options.provision_postgres and auto_provision and not get_database_url(project):
        emit(on_event, PipelineEvent("deploy.postgres", "running", "Provisioning PostgreSQL…"))
        try:
            postgres_provisioned = provision_postgres(
                project,
                provider=postgres_provider,
                reuse=True,
                apply_schema=not skip_stripe_schema,
            )
            emit(on_event, PipelineEvent("deploy.postgres", "ok", postgres_provisioned.get("message", "Done")))
        except (RuntimeError, ValueError, OSError) as exc:
            emit(on_event, PipelineEvent("deploy.postgres", "failed", str(exc)))
            next_steps.append(f"PostgreSQL: {exc}")

    postgres_connected = None
    db_url = get_database_url(project)
    if db_url:
        conn = test_postgres_connection(db_url)
        postgres_connected = conn["ok"]
        if not conn["ok"]:
            next_steps.append(f"Fix PostgreSQL: {conn['message']}")

    readiness_score = pipeline_result.readiness_score
    readiness_checks = pipeline_result.readiness_checks or []

    if readiness_checks and readiness_score is not None:
        report_md = format_readiness_report(readiness_checks, readiness_score)
        _write_text(root, "deploy/READINESS-REPORT.md", report_md)
        all_written.append("deploy/READINESS-REPORT.md")
        if readiness_score < 80:
            next_steps.append(
                f"Improve readiness score ({readiness_score}/100) — see deploy/READINESS-REPORT.md"
            )

    manifest = {
        "deployedAt": datetime.now(timezone.utc).isoformat(),
        "platform": platform,
        "productionUrl": prod_url,
        "postgresProvider": (scan.get("postgres") or {}).get("provider"),
        "readinessScore": readiness_score,
    }
    manifest_dir = root / ".stripe-installer"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "deploy-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    all_written.append(".stripe-installer/deploy-manifest.json")

    deploy_cfg["productionUrl"] = prod_url
    deploy_cfg["platform"] = platform
    deploy_cfg.setdefault("postgres", {})["provider"] = postgres_provider
    write_deploy_config(root, deploy_cfg)
    sync_project_from_config(project, deploy_cfg)
    all_written.append("deploy.config.json")

    if not prod_url or prod_url.startswith("http://localhost"):
        next_steps.append("Set production URL in project Settings")
    else:
        next_steps.append(f"Deploy: {platform_deploy_command(platform)}")
        health_path = (catalog_by_slug(project.slug or "") or {}).get("healthPath") or health_check_path(
            project.framework
        )
        next_steps.append(f"Verify: curl {prod_url}{health_path}")
    next_steps.append("Schedule backups: scripts/backup-db.sh or backup-db.ps1")

    env_push_result = None
    should_push_railway_env = options.push_railway_env and platform == "railway"
    if should_push_railway_env:
        emit(on_event, PipelineEvent("deploy.railway-env", "running", "Pushing env vars to Railway…"))
        try:
            from .env_push import auto_push_railway_env

            env_push_result = auto_push_railway_env(project)
            emit(
                on_event,
                PipelineEvent(
                    "deploy.railway-env",
                    "ok",
                    env_push_result.get("message", "Railway env vars updated"),
                ),
            )
            next_steps.insert(0, env_push_result.get("message", "Railway env vars updated"))
        except (RuntimeError, ValueError) as exc:
            emit(on_event, PipelineEvent("deploy.railway-env", "failed", str(exc)))
            next_steps.insert(0, f"Railway env push: {exc}")

    push_result = None
    if options.push_platform:
        emit(on_event, PipelineEvent("deploy.push", "running", f"Pushing to {platform}…"))
        push_result = push_to_platform(root, platform)
        if push_result["success"]:
            emit(on_event, PipelineEvent("deploy.push", "ok", push_result["message"]))
            next_steps.insert(0, push_result["message"])
        else:
            emit(on_event, PipelineEvent("deploy.push", "failed", push_result["message"]))
            next_steps.insert(0, f"Platform push failed: {push_result['message']}")

    label = readiness_label(readiness_score) if readiness_score is not None else "complete"
    emit(
        on_event,
        PipelineEvent(
            "run.completed",
            "ok",
            f"Deploy pipeline complete — {readiness_score or '?'}/100 {label}",
            score=readiness_score,
        ),
    )

    return DeployResult(
        pipeline=pipeline_result,
        files_written=all_written,
        next_steps=next_steps,
        platform=platform,
        production_url=prod_url,
        postgres_connected=postgres_connected,
        push_result=push_result,
        env_push_result=env_push_result,
        manifest=manifest,
    )
