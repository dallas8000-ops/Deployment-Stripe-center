"""Pre-deploy validation — catch vault/Railway issues before queuing Celery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.projects.models import Project
from apps.stripe_core.portfolio_catalog import catalog_by_slug, is_stripe_exempt_slug
from apps.vault.models import get_secret, hydrate_project_vault, vault_health

from .config import config_from_project
from .platform import detect_deploy_platform
from .railway_resolve import (
    _list_railway_projects,
    preset_for_project,
    resolve_railway_project_id,
    resolve_railway_web_service_id,
)


def _resolve_platform(project: Project, root: Path | None) -> str:
    scan = project.scan_data or {}
    if root and root.is_dir():
        cfg = config_from_project(project, root)
        platform = str(cfg.get("platform") or "unknown")
        if platform != "unknown":
            return platform
        return scan.get("deployPlatform") or detect_deploy_platform(root, project.framework)
    return scan.get("deployPlatform") or "unknown"


def run_deploy_preflight(
    project: Project,
    *,
    push_railway_env: bool = True,
    provision_postgres: bool = True,
    provision_stripe: bool = True,
) -> dict[str, Any]:
    """
    Validate deploy readiness before starting a pipeline run.
    Returns {ok, issues, warnings, platform, railway}.
    """
    issues: list[str] = []
    warnings: list[str] = []
    railway: dict[str, Any] = {}

    hydrate_project_vault(project)

    from apps.stripe_core.portfolio_workspace import ensure_project_workspace

    ensure_project_workspace(project)
    project.refresh_from_db(fields=["local_path"])

    health = vault_health(project)
    if health["unreadableCount"]:
        issues.append(
            f"{health['unreadableCount']} vault secret(s) cannot be decrypted — restore "
            f"~/.stripe-installer/projects/{project.slug}/vault.json or re-enter keys in Vault"
        )

    if not project.local_path:
        issues.append("Project local_path is not set — configure workspace path in Settings")
        return {"ok": False, "issues": issues, "warnings": warnings, "platform": "unknown", "railway": railway}

    root = Path(project.local_path).resolve()
    if not root.is_dir():
        issues.append(f"Project path not found: {root}")
        return {"ok": False, "issues": issues, "warnings": warnings, "platform": "unknown", "railway": railway}

    platform = _resolve_platform(project, root)
    stripe_exempt = is_stripe_exempt_slug(project.slug)

    if provision_stripe and not stripe_exempt and not get_secret(project, "STRIPE_SECRET_KEY"):
        issues.append("STRIPE_SECRET_KEY missing from vault — add keys or pull from Automation Center hub")

    if provision_postgres and platform == "railway":
        preset = preset_for_project(project)
        if preset and not get_secret(project, "DJANGO_SECRET_KEY"):
            warnings.append("DJANGO_SECRET_KEY missing — required for Django apps on Railway")

    if push_railway_env and platform == "railway":
        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        railway["hasToken"] = bool(token)
        if not token:
            issues.append(
                "RAILWAY_API_TOKEN missing from vault — create at https://railway.com/account/tokens"
            )
        else:
            stored_project_id = (get_secret(project, "RAILWAY_PROJECT_ID") or "").strip()
            stored_service_id = (get_secret(project, "RAILWAY_SERVICE_ID") or "").strip()
            railway["storedProjectId"] = stored_project_id or None
            railway["storedServiceId"] = stored_service_id or None

            project_id = stored_project_id or resolve_railway_project_id(project, token)
            if not project_id:
                try:
                    listed = _list_railway_projects(token)
                except RuntimeError as exc:
                    issues.append(f"Railway API error: {exc}")
                    listed = []
                if not listed:
                    warnings.append(
                        "Railway token returned no projects — token may be expired, project-scoped, "
                        "or from another account. Copy Project ID from Railway -> Project -> Settings and "
                        "save RAILWAY_PROJECT_ID in vault, then RAILWAY_SERVICE_ID for the web service."
                    )
                else:
                    names = ", ".join(p["name"] for p in listed[:5])
                    warnings.append(
                        f"Could not match Railway project to '{project.name}' — available: {names}. "
                        "Set RAILWAY_PROJECT_ID in vault."
                    )
            else:
                railway["resolvedProjectId"] = project_id
                service_id = stored_service_id or resolve_railway_web_service_id(project, token, project_id)
                if not service_id:
                    warnings.append(
                        "Railway web service ID not resolved — copy Service ID from the web service "
                        "(not Postgres) in Railway Settings and save RAILWAY_SERVICE_ID in vault."
                    )
                else:
                    railway["resolvedServiceId"] = service_id

    elif push_railway_env and platform == "unknown":
        catalog = catalog_by_slug(project.slug or "")
        prod_url = str((catalog or {}).get("productionUrl") or "")
        if ".railway.app" in prod_url:
            warnings.append(
                "Platform is 'unknown' but production URL is on Railway — env auto-push will be skipped. "
                "Set platform to 'railway' in deploy.config.json or re-run deploy to sync."
            )

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "platform": platform,
        "railway": railway,
    }
