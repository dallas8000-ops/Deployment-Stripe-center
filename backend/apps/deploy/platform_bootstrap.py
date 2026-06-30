"""In-app platform automation — vault, Railway env, and deploy metadata without manual dashboard steps."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.projects.models import Project
from apps.vault.master_key import (
    master_key_path,
    sync_local_master_key_from_env,
    vault_master_key_status,
)
from apps.vault.models import get_secret, hydrate_project_vault, vault_health


def _hub_railway_token(project: Project) -> str:
    token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
    if token:
        return token
    server = (getattr(settings, "RAILWAY_API_TOKEN", "") or "").strip()
    return server


def _host_railway_ids(project: Project) -> tuple[str, str, str]:
    """Resolve Railway project/service/environment for the running service or hub vault."""
    project_id = (
        os.environ.get("RAILWAY_PROJECT_ID", "").strip()
        or (getattr(settings, "RAILWAY_PROJECT_ID", "") or "").strip()
        or (get_secret(project, "RAILWAY_PROJECT_ID") or "").strip()
    )
    service_id = (
        os.environ.get("RAILWAY_SERVICE_ID", "").strip()
        or (get_secret(project, "RAILWAY_SERVICE_ID") or "").strip()
    )
    environment_id = os.environ.get("RAILWAY_ENVIRONMENT_ID", "").strip()
    return project_id, service_id, environment_id


def sync_deploy_platform_from_disk(project: Project) -> str | None:
    """Read deploy.config.json and sync platform/URL into project scan_data."""
    if not project.local_path:
        return sync_platform_from_catalog(project)
    root = Path(project.local_path).resolve()
    if not root.is_dir():
        return sync_platform_from_catalog(project)
    from apps.deploy.config import config_from_project, sync_project_from_config

    cfg = config_from_project(project, root)
    platform = str(cfg.get("platform") or "unknown")
    if platform == "unknown":
        return sync_platform_from_catalog(project)
    sync_project_from_config(project, cfg)
    return platform


def sync_platform_from_catalog(project: Project) -> str | None:
    """When deploy.config.json is missing, infer Railway from portfolio catalog production URL."""
    from apps.projects.scan_data_utils import update_project_scan_data
    from apps.stripe_core.portfolio_catalog import catalog_by_slug

    catalog = catalog_by_slug(project.slug or "")
    if not catalog:
        return None
    prod = str(catalog.get("productionUrl") or "").strip().rstrip("/")
    if ".railway.app" not in prod:
        return None
    update_project_scan_data(
        project,
        {
            "deployPlatform": "railway",
            "productionUrl": prod,
        },
    )
    return "railway"


def pin_vault_master_key_to_railway(project: Project) -> dict[str, Any]:
    """Push VAULT_MASTER_KEY to this Railway service so redeploys keep secrets readable."""
    from apps.deploy.env_push import push_to_railway

    status = vault_master_key_status()
    master_key = (settings.VAULT_MASTER_KEY or "").strip()
    if not master_key:
        raise RuntimeError("No vault master key available to pin")

    token = _hub_railway_token(project)
    if not token:
        raise RuntimeError(
            "RAILWAY_API_TOKEN required — add to hub vault or Railway service variables once, "
            "then use Automate platform setup again"
        )

    project_id, service_id, environment_id = _host_railway_ids(project)
    if not project_id or not service_id:
        from apps.deploy.railway_resolve import (
            remember_railway_targets,
            resolve_railway_project_id,
            resolve_railway_web_service_id,
        )

        project_id = project_id or (resolve_railway_project_id(project, token) or "")
        if project_id and not service_id:
            service_id = resolve_railway_web_service_id(project, token, project_id) or ""
        if project_id and service_id:
            remember_railway_targets(project, project_id, service_id)

    if not project_id or not service_id:
        raise RuntimeError(
            "Could not resolve Railway project/service for this app — save RAILWAY_PROJECT_ID and "
            "RAILWAY_SERVICE_ID in hub vault once, then retry Automate platform setup"
        )

    result = push_to_railway(
        token,
        project_id,
        service_id,
        {"VAULT_MASTER_KEY": master_key},
        environment_id or None,
        preserve_existing=True,
    )
    return {
        "pinned": True,
        "projectId": project_id,
        "serviceId": service_id,
        "wasStable": status["stable"],
        "message": "VAULT_MASTER_KEY pinned on Railway — redeploys will keep vault secrets readable",
        "merge": result.get("merge"),
    }


def reconcile_local_master_key() -> dict[str, Any]:
    """Align local master key sources (file is canonical when both exist)."""
    status = vault_master_key_status()
    path = master_key_path()

    if status["onRailway"]:
        return {
            "action": "none",
            "message": status["detail"],
            "status": status,
        }

    if status["hasEnvKey"] and not status["hasFileKey"]:
        sync_local_master_key_from_env()
        return {
            "action": "env_to_file",
            "message": f"Persisted VAULT_MASTER_KEY from environment to {path}",
            "status": vault_master_key_status(),
        }

    if status["hasFileKey"] and status["hasEnvKey"] and not status["keysMatch"]:
        return {
            "action": "mismatch",
            "message": (
                f"Local .env and {path} use different keys — update backend/.env VAULT_MASTER_KEY "
                "to match the file (hub secrets use the file key)"
            ),
            "status": status,
            "filePath": str(path),
        }

    return {
        "action": "ok",
        "message": status["detail"],
        "status": status,
    }


def platform_automation_status(project: Project) -> dict[str, Any]:
    """Checklist for in-app automation (shown in Setup Hub)."""
    key_status = vault_master_key_status()
    health = vault_health(project)
    scan = project.scan_data or {}
    platform = scan.get("deployPlatform") or "unknown"
    if platform == "unknown" and project.local_path:
        platform = sync_deploy_platform_from_disk(project) or "unknown"

    token = _hub_railway_token(project)
    project_id, service_id, _ = _host_railway_ids(project)
    railway_detected = False
    railway_message = ""
    if token:
        from apps.deploy.railway_resolve import ensure_railway_targets_detected

        try:
            detection = ensure_railway_targets_detected(project, token)
        except Exception as exc:
            # This function feeds a read-only status view. A provider outage,
            # DNS failure, or expired token must not take the page down.
            railway_message = f"Railway discovery unavailable: {exc}"
        else:
            project_id = detection.get("projectId") or project_id
            service_id = detection.get("serviceId") or service_id
            railway_detected = bool(detection.get("detected"))
            railway_message = str(detection.get("message") or "")

    return {
        "masterKey": {
            "stable": key_status["stable"],
            "source": key_status["source"],
            "detail": key_status["detail"],
            "keysMatch": key_status["keysMatch"],
            "onRailway": key_status["onRailway"],
        },
        "vault": health,
        "deployPlatform": platform,
        "railway": {
            "hasToken": bool(token),
            "projectId": project_id or None,
            "serviceId": service_id or None,
            "canPinMasterKey": bool(token and (project_id or token)),
            "detected": railway_detected,
            "detectionMessage": railway_message,
        },
        "ready": health["unreadableCount"] == 0 and key_status["stable"],
    }


def prepare_project_automation(project: Project, *, user=None) -> dict[str, Any]:
    """
    Default prep that should run before every pipeline/deploy — built-in, not optional.
    Hydrates vault, syncs platform metadata, pulls hub keys, reconciles master key on hub.
    """
    from apps.stripe_core.hub_keys import (
        HUB_SLUG,
        pull_stripe_keys_for_user,
        repair_project_vault_from_hub,
        sync_deploy_keys_to_portfolio_projects,
    )

    steps: list[dict[str, str]] = []

    if project.slug == HUB_SLUG:
        key_result = reconcile_local_master_key()
        if key_result.get("action") == "mismatch":
            steps.append({"step": "master_key", "detail": key_result["message"]})
        elif key_result.get("action") != "none":
            steps.append({"step": "master_key", "detail": key_result.get("message", "Master key OK")})

    imported = hydrate_project_vault(project)
    if imported:
        steps.append({"step": "hydrate", "detail": f"Restored {len(imported)} key(s) from backup/env"})

    if user and project.slug != HUB_SLUG:
        hub = Project.objects.filter(owner=project.owner, slug=HUB_SLUG).first()
        if hub:
            repaired = repair_project_vault_from_hub(project, hub)
            if repaired:
                steps.append({"step": "hub_repair", "detail": f"Restored {len(repaired)} key(s) from hub"})
        copied = pull_stripe_keys_for_user(project, user)
        if copied:
            steps.append({"step": "hub_keys", "detail": f"Pulled {len(copied)} key(s) from hub"})

    platform = sync_deploy_platform_from_disk(project)
    if platform:
        steps.append({"step": "platform", "detail": f"Platform synced from deploy.config.json ({platform})"})

    return {"steps": steps, "platform": platform or (project.scan_data or {}).get("deployPlatform")}


def automate_project_deploy(project: Project, *, user=None) -> dict[str, Any]:
    """
    One-click deploy automation for a project:
    hydrate vault, sync platform metadata, pull hub keys, push Railway env vars.
    """
    from apps.deploy.preflight import run_deploy_preflight
    from apps.deploy.railway_resolve import preset_for_project

    prep = prepare_project_automation(project, user=user)
    steps: list[dict[str, Any]] = [
        {"step": s["step"], "ok": True, "detail": s["detail"]} for s in prep["steps"]
    ]

    preflight = run_deploy_preflight(
        project,
        push_railway_env=True,
        provision_stripe=project.slug != "stripe-installer",
    )
    steps.append({"step": "preflight", "ok": preflight["ok"], "detail": "; ".join(preflight["issues"] or ["OK"])})

    env_push = None
    if preflight["platform"] == "railway" and not preflight["issues"]:
        from apps.deploy.env_push import auto_push_railway_env

        try:
            env_push = auto_push_railway_env(project, preset=preset_for_project(project))
            deploy = (env_push or {}).get("railwayDeploy") or {}
            detail = env_push.get("message", "Env vars pushed")
            if deploy.get("repoConnected"):
                detail += f"; GitHub linked ({deploy.get('connectedRepo')})"
            if deploy.get("deployTriggered"):
                detail += f"; deploy {deploy.get('deploymentId')}"
            elif not deploy.get("currentRepo") and not deploy.get("repoConnected"):
                detail += "; WARNING: no GitHub repo on Railway — git push will not redeploy"
            steps.append(
                {
                    "step": "railway_env_push",
                    "ok": True,
                    "detail": detail,
                }
            )
        except (RuntimeError, ValueError) as exc:
            steps.append({"step": "railway_env_push", "ok": False, "detail": str(exc)})

    return {
        "ok": preflight["ok"] and (env_push is not None or preflight["platform"] != "railway"),
        "steps": steps,
        "preflight": preflight,
        "envPush": env_push,
        "platform": preflight["platform"],
    }


def bootstrap_new_project(project: Project, *, user) -> dict[str, Any]:
    """
    Run after create (or when local_path is set): repair paths, sync metadata,
    pull hub keys, and push Railway env when the project folder exists.
    """
    from django.utils import timezone

    from apps.deploy.automation_gate import run_automation_before_pipeline
    from apps.projects.scan_data_utils import update_project_scan_data
    from apps.stripe_core.portfolio_workspace import reconcile_hub_workspace, sync_portfolio_scan_metadata

    reconcile_hub_workspace(project)
    sync_portfolio_scan_metadata(project)
    project.refresh_from_db(fields=["local_path", "scan_data"])

    if not (project.local_path or "").strip():
        update_project_scan_data(
            project,
            {
                "lastAutomationAt": timezone.now().isoformat(),
                "lastAutomationOk": False,
                "lastAutomationMessage": "Set local_path to your real app folder to finish automation.",
            },
        )
        return {"ok": False, "skipped": True, "message": "local_path required for automation"}

    auto = run_automation_before_pipeline(project, user=user, hub_bootstrap=False)
    update_project_scan_data(
        project,
        {
            "lastAutomationAt": timezone.now().isoformat(),
            "lastAutomationOk": auto.get("ok", False),
            "lastAutomationMessage": auto.get("message", ""),
        },
    )
    return auto


def bootstrap_platform_automation(hub: Project, *, user) -> dict[str, Any]:
    """
    Hub-only: reconcile master key, pin to Railway, sync all owned projects, push env where ready.
    """
    from apps.stripe_core.hub_keys import (
        HUB_SLUG,
        repair_project_vault_from_hub,
        sync_deploy_keys_to_portfolio_projects,
        sync_vault_to_billing_projects,
    )
    from apps.stripe_core.portfolio_catalog import is_merged_legacy_slug
    from apps.stripe_core.provision import retire_legacy_stripe_webhooks

    if hub.slug != HUB_SLUG:
        raise ValueError("Platform bootstrap runs on the Automation Center hub project only")

    results: dict[str, Any] = {"hubSlug": hub.slug, "actions": []}

    key_result = reconcile_local_master_key()
    results["actions"].append({"action": "reconcile_master_key", **key_result})

    try:
        retired = retire_legacy_stripe_webhooks()
        results["actions"].append(
            {"action": "retire_legacy_webhooks", "ok": True, "retired": retired, "count": len(retired)}
        )
    except Exception as exc:
        results["actions"].append({"action": "retire_legacy_webhooks", "ok": False, "detail": str(exc)})

    pin_result = None
    try:
        pin_result = pin_vault_master_key_to_railway(hub)
        results["actions"].append({"action": "pin_master_key_railway", "ok": True, **pin_result})
    except RuntimeError as exc:
        results["actions"].append({"action": "pin_master_key_railway", "ok": False, "detail": str(exc)})

    vault_sync = sync_vault_to_billing_projects(hub, user)
    results["actions"].append({"action": "sync_vault_to_projects", **vault_sync})

    portfolio_sync = sync_deploy_keys_to_portfolio_projects(hub, user)
    results["actions"].append({"action": "sync_portfolio_deploy_keys", **portfolio_sync})

    from apps.stripe_core.portfolio_workspace import repair_portfolio_local_path

    project_results: list[dict[str, Any]] = []
    for project in Project.objects.filter(owner=hub.owner).order_by("slug"):
        if project.slug == HUB_SLUG or is_merged_legacy_slug(project.slug):
            continue
        repair_portfolio_local_path(project)
        hydrate_project_vault(project)
        repair_project_vault_from_hub(project, hub)
        sync_deploy_platform_from_disk(project)
        deploy_result = automate_project_deploy(project, user=user)
        project_results.append(
            {
                "slug": project.slug,
                "ok": deploy_result["ok"],
                "platform": deploy_result["platform"],
                "steps": deploy_result["steps"],
            }
        )

    results["projects"] = project_results
    results["automationStatus"] = platform_automation_status(hub)
    railway_projects = [p for p in project_results if p["platform"] == "railway"]
    results["ok"] = key_result.get("action") != "mismatch" and (
        not railway_projects or all(p["ok"] for p in railway_projects)
    )
    results["message"] = (
        "Platform automation complete"
        if results["ok"]
        else "Platform automation finished with issues — review steps below"
    )
    return results
