"""In-app Automation Center setup — reset, portfolio audit, webhook registration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings

from apps.core.access import projects_for_user
from apps.projects.models import Project
from apps.stripe_installer.portfolio_audit import (
    fix_webhooks_for_projects,
    run_portfolio_audit,
    write_portfolio_report,
)
from apps.stripe_installer.portfolio_catalog import (
    catalog_by_slug,
    catalog_summary,
    is_stripe_exempt_slug,
)
from apps.stripe_installer.hub_keys import (
    HUB_SLUG,
    portfolio_app_for_project,
    pull_stripe_keys_for_user,
    resolve_production_app_url,
    sync_vault_to_billing_projects,
)
from apps.stripe_installer.portfolio_paths import portfolio_registry_path
from apps.stripe_installer.portfolio_registry import PortfolioApp, load_registry
from apps.stripe_installer.portfolio_sync import sync_portfolio_registry
from apps.stripe_installer.stripe_config import write_stripe_config
from apps.stripe_installer.verify import verify_stripe_keys
from apps.vault.models import VaultSecret, get_secret, set_secret, vault_health

PROJECT_NAME = "Deployment & Stripe Automation Center"
REGISTRY_ID = "automation-center"
PRODUCTION_URL = "https://stripe-installer-production.up.railway.app"
WEBHOOK_PATH = "/api/v1/billing/webhook/"


def default_production_url() -> str:
    return PRODUCTION_URL


def reset_workspace(project: Project, *, clear_vault: bool = False) -> dict[str, Any]:
    """Refresh project metadata, portfolio registry, and stripe.config.json."""
    repo_root = Path(settings.REPO_ROOT)
    local_path = str(repo_root)

    changed: list[str] = []
    if project.name != PROJECT_NAME:
        project.name = PROJECT_NAME
        changed.append("name")
    if project.local_path != local_path:
        project.local_path = local_path
        changed.append("localPath")
    if changed:
        project.save(update_fields=changed + ["updated_at"])

    owner_projects = list(Project.objects.filter(owner=project.owner))
    sync_result = sync_portfolio_registry(owner_projects)
    reg_path = portfolio_registry_path()

    config_path = write_stripe_config(
        repo_root,
        {
            "appUrl": PRODUCTION_URL,
            "provision": {
                "reuseExisting": True,
                "createWebhook": True,
                "createPortal": True,
            },
        },
    )

    cleared = 0
    if clear_vault:
        cleared, _ = VaultSecret.objects.filter(project=project).delete()

    return {
        "projectSlug": project.slug,
        "projectName": project.name,
        "localPath": local_path,
        "registryPath": str(reg_path),
        "stripeConfigPath": str(config_path),
        "vaultSecretsCleared": cleared,
        "expectedWebhookUrl": f"{PRODUCTION_URL.rstrip('/')}{WEBHOOK_PATH}",
        "portfolioSummary": sync_result.get("portfolioSummary"),
        "registryAppCount": sync_result.get("appCount"),
    }


def audit_stripe_account(project: Project) -> dict[str, Any]:
    secret = get_secret(project, "STRIPE_SECRET_KEY")
    publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
    if not secret:
        raise ValueError("Add STRIPE_SECRET_KEY to the project vault first.")

    registry = load_registry()
    data = run_portfolio_audit(
        secret_key=secret,
        publishable_key=publishable,
        registry_apps=registry,
    )
    md_path, json_path = write_portfolio_report(data)
    scan_data = dict(project.scan_data or {})
    scan_data["lastPortfolioAuditAt"] = data.get("scannedAt")
    scan_data["lastPortfolioAuditSummary"] = data.get("summary")
    scan_data["lastPortfolioAuditRegistryGaps"] = data.get("registryGaps") or []
    project.scan_data = scan_data
    project.save(update_fields=["scan_data", "updated_at"])
    return {
        **data,
        "reportMarkdownPath": str(md_path),
        "reportJsonPath": str(json_path),
    }


def register_webhooks_for_user(user, *, dry_run: bool = False) -> list[dict[str, Any]]:
    registry = [a for a in load_registry() if a.requires_stripe_webhook]
    projects = list(Project.objects.filter(owner=user))
    return fix_webhooks_for_projects(projects, registry, dry_run=dry_run)


def sync_registry_for_user(user) -> dict[str, Any]:
    projects = list(projects_for_user(user))
    return sync_portfolio_registry(projects)


def setup_hub_status(project: Project, *, user=None) -> dict[str, Any]:
    if user and project.slug != HUB_SLUG and not get_secret(project, "STRIPE_SECRET_KEY"):
        pull_stripe_keys_for_user(project, user)

    health = vault_health(project)
    secret = get_secret(project, "STRIPE_SECRET_KEY")
    publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
    verification = verify_stripe_keys(secret, publishable)

    registry = load_registry()
    app_entry = portfolio_app_for_project(project)
    expected_webhook = app_entry.webhook_url if app_entry else f"{PRODUCTION_URL.rstrip('/')}{WEBHOOK_PATH}"
    app_registry_id = app_entry.id if app_entry else REGISTRY_ID
    production_url = (
        app_entry.production_url
        if app_entry and app_entry.production_url
        else resolve_production_app_url(project) or PRODUCTION_URL
    )

    scan_data = project.scan_data or {}
    last_summary = scan_data.get("lastPortfolioAuditSummary")
    registry_gaps = scan_data.get("lastPortfolioAuditRegistryGaps") or []
    project_gaps = [
        g
        for g in registry_gaps
        if g.get("app") == app_registry_id or g.get("expectedUrl") == expected_webhook
    ]

    stripe_config_exists = False
    if project.local_path:
        stripe_config_exists = (Path(project.local_path) / "stripe.config.json").is_file()

    webhook_ok = bool(last_summary) and not project_gaps
    webhook_detail = expected_webhook
    if is_stripe_exempt_slug(project.slug):
        webhook_ok = True
        webhook_detail = "Portfolio exempt — no Stripe subscription billing for this app"
    elif not last_summary:
        webhook_detail = "Run Scan Stripe account on Automation Center hub"
    elif project_gaps:
        webhook_detail = project_gaps[0].get("issue") or expected_webhook

    steps = [
        {
            "id": "vault",
            "label": "Vault secrets readable",
            "ok": health["unreadableCount"] == 0 and bool(secret),
            "detail": (
                f"{health['unreadableCount']} unreadable secret(s)"
                if health["unreadableCount"]
                else ("Add STRIPE_SECRET_KEY" if not secret else "OK")
            ),
        },
        {
            "id": "keys",
            "label": "Stripe API keys valid",
            "ok": verification.secret_key.valid,
            "detail": verification.secret_key.message,
        },
        {
            "id": "config",
            "label": "stripe.config.json present",
            "ok": stripe_config_exists,
            "detail": "Run full setup pipeline to generate" if project.slug != HUB_SLUG else "Run Reset workspace if missing",
        },
        {
            "id": "webhook",
            "label": "Webhook registered in Stripe",
            "ok": webhook_ok,
            "detail": webhook_detail,
        },
    ]

    return {
        "projectSlug": project.slug,
        "projectName": project.name,
        "vaultHealth": health,
        "verification": verification.to_public_dict(),
        "registryPath": str(portfolio_registry_path()),
        "registryApp": app_entry.to_dict() if app_entry else None,
        "expectedWebhookUrl": expected_webhook,
        "productionUrl": production_url,
        "lastPortfolioAuditSummary": last_summary,
        "lastPortfolioAuditRegistryGaps": registry_gaps,
        "steps": steps,
        "readyForPipeline": all(s["ok"] for s in steps if s["id"] in {"vault", "keys"}),
        "portfolioSummary": catalog_summary(),
        "stripeExempt": is_stripe_exempt_slug(project.slug),
        "isHubProject": project.slug == HUB_SLUG,
        "hubSlug": HUB_SLUG,
    }
