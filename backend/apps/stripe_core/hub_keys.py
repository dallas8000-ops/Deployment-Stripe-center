"""Pull portfolio Stripe keys from the Automation Center hub project."""

from __future__ import annotations

from typing import Any

from apps.projects.models import Project
from apps.stripe_core.portfolio_catalog import (
    HUB_SLUG,
    catalog_by_slug,
    catalog_live_urls,
    is_stripe_exempt_slug,
    stripe_billing_apps,
)
from apps.stripe_core.portfolio_registry import PortfolioApp, load_registry
from apps.vault.models import get_secret, set_secret

STRIPE_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "STRIPE_SECRET_KEY": ("STRIPE_SECRET_KEY", "SAAS_STRIPE_SECRET_KEY"),
    "STRIPE_PUBLISHABLE_KEY": ("STRIPE_PUBLISHABLE_KEY", "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY"),
    "STRIPE_WEBHOOK_SECRET": ("STRIPE_WEBHOOK_SECRET", "SAAS_STRIPE_WEBHOOK_SECRET"),
    "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY": (
        "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
        "STRIPE_PUBLISHABLE_KEY",
    ),
}

STRIPE_KEYS_TO_SYNC = tuple(STRIPE_KEY_ALIASES.keys())

# Copied from hub to child projects during platform bootstrap (never hub-specific Railway IDs).
HUB_SHARED_DEPLOY_KEYS = ("RAILWAY_API_TOKEN", "DJANGO_SECRET_KEY")


def get_hub_project(owner) -> Project | None:
    return Project.objects.filter(owner=owner, slug=HUB_SLUG).first()


def resolve_production_app_url(project: Project) -> str:
    """Railway API URL for webhooks/provision — not the local Django dev server."""
    for app in load_registry():
        if app.project_slug == project.slug and app.production_url:
            return app.production_url.rstrip("/")

    catalog = catalog_by_slug(project.slug)
    if catalog and catalog.get("productionUrl"):
        return str(catalog["productionUrl"]).rstrip("/")

    scan = project.scan_data or {}
    url = str(scan.get("productionUrl") or scan.get("production_url") or "").strip()
    return url.rstrip("/")


def resolve_web_app_url(project: Project) -> str:
    """Railway web frontend URL — billing return URL, CLIENT_URL, live demo."""
    live = catalog_live_urls(catalog_by_slug(project.slug or ""))
    if live.get("webUrl"):
        return live["webUrl"]

    scan = project.scan_data or {}
    url = str(scan.get("webProductionUrl") or scan.get("web_production_url") or "").strip()
    if url:
        return url.rstrip("/")
    return resolve_production_app_url(project)


def resolve_demo_app_url(project: Project) -> str:
    """Railway /demo URL for live view; portfolio may use portfolioDemoUrl separately."""
    live = catalog_live_urls(catalog_by_slug(project.slug or ""))
    if live.get("demoUrl"):
        return live["demoUrl"]
    web = resolve_web_app_url(project)
    return f"{web.rstrip('/')}/demo" if web else ""


def portfolio_app_for_project(project: Project) -> PortfolioApp | None:
    catalog = catalog_by_slug(project.slug)
    for app in load_registry():
        if app.project_slug == project.slug:
            if catalog:
                if not app.production_url and catalog.get("productionUrl"):
                    app.production_url = str(catalog["productionUrl"]).rstrip("/")
                if not app.local_path and catalog.get("defaultLocalPath"):
                    app.local_path = str(catalog["defaultLocalPath"])
            return app
    if not catalog or catalog.get("merged"):
        return None
    return PortfolioApp(
        id=str(catalog["id"]),
        name=str(catalog["name"]),
        production_url=str(catalog.get("productionUrl") or "").rstrip("/"),
        webhook_path=str(catalog.get("webhookPath") or "/stripe/webhook"),
        health_path=str(catalog.get("healthPath") or "/health/"),
        project_slug=project.slug,
        local_path=str(catalog.get("defaultLocalPath") or project.local_path or ""),
        stripe_exempt=bool(catalog.get("stripeExempt")),
        notes=str(catalog.get("notes") or ""),
    )


def hub_key_value(hub: Project, canonical_key: str) -> str | None:
    for key in STRIPE_KEY_ALIASES.get(canonical_key, (canonical_key,)):
        value = get_secret(hub, key)
        if value:
            return value
    return None


def pull_stripe_keys_from_hub(
    target: Project,
    hub: Project | None = None,
    *,
    overwrite: bool = False,
) -> list[str]:
    """Copy Stripe keys from hub vault into target (server-side). Returns keys copied."""
    if target.slug == HUB_SLUG or is_stripe_exempt_slug(target.slug):
        return []
    if hub is None:
        hub = get_hub_project(target.owner)
    if not hub or hub.id == target.id:
        return []

    copied: list[str] = []
    for key in STRIPE_KEYS_TO_SYNC:
        if not overwrite and get_secret(target, key):
            continue
        value = hub_key_value(hub, key)
        if not value:
            continue
        set_secret(target, key, value)
        copied.append(key)
    return copied


def pull_stripe_keys_for_user(target: Project, user) -> list[str]:
    hub = get_hub_project(user)
    return pull_stripe_keys_from_hub(target, hub)


def _secret_needs_repair(project: Project, key: str) -> bool:
    from apps.vault.models import VaultSecret, is_secret_readable

    if get_secret(project, key):
        return False
    row = VaultSecret.objects.filter(project=project, key_name=key).first()
    return row is not None and not is_secret_readable(project, row)


def repair_project_vault_from_hub(target: Project, hub: Project | None = None) -> list[str]:
    """Restore unreadable or missing keys from the hub vault (Stripe + shared deploy tokens)."""
    if target.slug == HUB_SLUG or is_stripe_exempt_slug(target.slug):
        return []
    if hub is None:
        hub = get_hub_project(target.owner)
    if not hub or hub.id == target.id:
        return []

    copied: list[str] = []
    from apps.vault.models import delete_secret, vault_health

    force = vault_health(target)["unreadableCount"] > 0

    for key in STRIPE_KEYS_TO_SYNC:
        if not force and get_secret(target, key) and not _secret_needs_repair(target, key):
            continue
        if _secret_needs_repair(target, key):
            delete_secret(target, key)
        value = hub_key_value(hub, key)
        if not value:
            continue
        set_secret(target, key, value)
        copied.append(key)

    for key in HUB_SHARED_DEPLOY_KEYS:
        if not force and get_secret(target, key) and not _secret_needs_repair(target, key):
            continue
        if _secret_needs_repair(target, key):
            delete_secret(target, key)
        value = get_secret(hub, key)
        if not value:
            continue
        set_secret(target, key, value)
        copied.append(key)

    return copied


def sync_vault_to_billing_projects(hub: Project, user) -> dict[str, Any]:
    from apps.stripe_core.portfolio_catalog import DASHBOARD_HIDDEN_PROJECT_SLUGS

    billing_slugs = {e.get("projectSlug") for e in stripe_billing_apps() if e.get("projectSlug")}
    billing_slugs.discard(hub.slug)

    projects = [
        p
        for p in Project.objects.filter(owner=user)
        if p.slug in billing_slugs and p.slug not in DASHBOARD_HIDDEN_PROJECT_SLUGS
    ]

    results: list[dict[str, Any]] = []
    for target in projects:
        copied = repair_project_vault_from_hub(target, hub)
        if not copied:
            copied = pull_stripe_keys_from_hub(target, hub, overwrite=False)
        results.append(
            {
                "projectSlug": target.slug,
                "projectName": target.name,
                "copiedKeys": copied,
                "ok": bool(copied) or bool(get_secret(target, "STRIPE_SECRET_KEY")),
            }
        )
    return {"hubSlug": hub.slug, "results": results}


def sync_deploy_keys_to_portfolio_projects(hub: Project, user) -> dict[str, Any]:
    """Sync Railway token + Django secret to portfolio Railway demos (SilverFox, Kistie, …)."""
    from apps.stripe_core.portfolio_catalog import PORTFOLIO_CATALOG

    slugs = {
        str(e.get("projectSlug") or "")
        for e in PORTFOLIO_CATALOG
        if e.get("stripeExempt") and ".railway.app" in str(e.get("productionUrl") or "")
    }
    slugs.discard("")

    results: list[dict[str, Any]] = []
    for target in Project.objects.filter(owner=user, slug__in=slugs):
        copied: list[str] = []
        for key in HUB_SHARED_DEPLOY_KEYS:
            value = get_secret(hub, key)
            if not value:
                continue
            set_secret(target, key, value)
            copied.append(key)
        results.append(
            {
                "projectSlug": target.slug,
                "copiedKeys": copied,
                "ok": bool(get_secret(target, "RAILWAY_API_TOKEN")),
            }
        )
    return {"hubSlug": hub.slug, "results": results}
