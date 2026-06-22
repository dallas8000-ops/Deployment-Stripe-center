"""Canonical Gilliom portfolio apps — Stripe billing vs exempt storefronts/APIs."""

from __future__ import annotations

from typing import Any, TypedDict


class CatalogEntry(TypedDict, total=False):
    id: str
    name: str
    productionUrl: str
    """API / backend host (webhooks, health)."""
    webProductionUrl: str
    """Frontend host on Railway — live view and Stripe customer return URL."""
    demoUrl: str
    """Railway live demo route (e.g. /demo). Primary live experience."""
    portfolioDemoUrl: str
    """Optional custom domain URL for portfolio Live demo button only (CNAME → Railway web)."""
    defaultLocalPath: str
    webhookPath: str
    healthPath: str
    projectSlug: str
    stripeExempt: bool
    merged: bool
    notes: str


# Slugs hidden from the Projects dashboard (merged into a canonical project).
MERGED_LEGACY_PROJECT_SLUGS: frozenset[str] = frozenset(
    {
        "api-transfer",
        "api_transfer",
        "elite-fintech-web",
    }
)

# Legacy slug → canonical hub project slug (for redirects and automation).
MERGED_INTO_PROJECT_SLUGS: dict[str, str] = {
    "api-transfer": "stripe-installer",
    "api_transfer": "stripe-installer",
    "elite-fintech-web": "elite-fintech-systems",
}

HUB_SLUG = "stripe-installer"

STRIPE_EXEMPT_SLUGS: frozenset[str] = frozenset(
    {
        "kistie-store",
        "silverfox",
        "blog-2",
        "react-store-catalog",
    }
)

# Portfolio demos — not Stripe billing workspaces; hide from Projects dashboard.
DASHBOARD_HIDDEN_PROJECT_SLUGS: frozenset[str] = MERGED_LEGACY_PROJECT_SLUGS | STRIPE_EXEMPT_SLUGS

# Matches FrontlineDigital portfolioLiveUrls.ts (Railway hostnames for webhooks/audit).
PORTFOLIO_CATALOG: list[CatalogEntry] = [
    {
        "id": "automation-center",
        "name": "Deployment & Stripe Automation Center",
        "productionUrl": "https://stripe-installer-production.up.railway.app",
        "webhookPath": "/api/v1/billing/webhook/",
        "healthPath": "/health/",
        "projectSlug": "stripe-installer",
        "notes": "Unified Stripe setup + deploy hub",
    },
        {
            "id": "elite-fintech",
            "name": "Elite Fintech Systems",
            "productionUrl": "https://elite-fintech-api-production.up.railway.app",
            "webProductionUrl": "https://elite-fintech-web-production.up.railway.app",
            "demoUrl": "https://elite-fintech-web-production.up.railway.app/demo",
            "webhookPath": "/webhooks/stripe/",
            "healthPath": "/health/",
            "projectSlug": "elite-fintech-systems",
            "defaultLocalPath": r"C:\Software Projects\Elite Fintech Systems",
            "notes": (
                "One Railway project (portfolio hub) — three services: "
                "elite-fintech-systems-api, -web, -db. Same monorepo, not a separate project."
            ),
        },
    {
        "id": "kistie-store",
        "name": "Kistie Store",
        "productionUrl": "https://kistie-store-production.up.railway.app",
        "healthPath": "/health/",
        "projectSlug": "kistie-store",
        "defaultLocalPath": r"C:\Software Projects\Kristie-Store",
        "stripeExempt": True,
        "notes": "Portfolio exempt — no Stripe subscription billing",
    },
    {
        "id": "silverfox",
        "name": "SilverFox",
        "productionUrl": "https://silverfox-production.up.railway.app",
        "healthPath": "/health/",
        "projectSlug": "silverfox",
        "defaultLocalPath": r"C:\Software Projects\SilverFox",
        "stripeExempt": True,
        "notes": "Men's fashion e-commerce — Django SSR, live FX, Stripe checkout planned",
    },
    {
        "id": "blog-api",
        "name": "Django REST Blog API",
        "productionUrl": "https://blog-2-production-72bc.up.railway.app",
        "healthPath": "/health/",
        "projectSlug": "blog-2",
        "defaultLocalPath": r"C:\Software Projects\Blog-2",
        "stripeExempt": True,
        "notes": "Portfolio exempt — content API, no paid Stripe catalog",
    },
    {
        "id": "react-store-catalog",
        "name": "React Store Catalog",
        "productionUrl": "https://react-store-catalog-1-production.up.railway.app",
        "webhookPath": "/api/stripe/webhook",
        "healthPath": "/health/",
        "projectSlug": "react-store-catalog",
        "defaultLocalPath": r"C:\Software Projects\React-Store-Catalog",
        "stripeExempt": True,
        "notes": "Portfolio exempt — catalog demo, not a paid Stripe product",
    },
    {
        "id": "righand",
        "name": "RIGHAND",
        "productionUrl": "https://righand-production.up.railway.app",
        "webhookPath": "/api/v1/billing/webhook/",
        "healthPath": "/health/",
        "projectSlug": "righand",
    },
    {
        "id": "pc-checker-extreme",
        "name": "PC Checker Extreme",
        "productionUrl": "https://pc-checker-extreme-production.up.railway.app",
        "webhookPath": "/api/v1/billing/webhook/",
        "healthPath": "/health/",
        "projectSlug": "pc-checker-extreme",
    },
    {
        "id": "dbops",
        "name": "DBOps Control Center",
        "productionUrl": "https://dbops-api-production-5047.up.railway.app",
        "webhookPath": "/api/v1/billing/webhook/",
        "healthPath": "/health/",
        "projectSlug": "dbops-control-center",
        "defaultLocalPath": r"C:\Software Projects\DBOps-Control-Center",
        "notes": "Webhook on API service (not dbops-web frontend)",
    },
    {
        "id": "specwright",
        "name": "Specwright",
        "productionUrl": "https://specwright-api-production.up.railway.app",
        "webhookPath": "/api/v1/billing/webhook/",
        "healthPath": "/health/",
        "projectSlug": "specwright",
        "defaultLocalPath": r"C:\Software Projects\Specwright",
        "notes": "Webhook on API service (not specwright-web frontend)",
    },
    {
        "id": "enpowercommand",
        "name": "EnPowerCommand",
        "productionUrl": "https://enpowercommand-production.up.railway.app",
        "webhookPath": "/api/v1/billing/webhook/",
        "healthPath": "/health/",
        "projectSlug": "enpowercommand",
    },
    {
        "id": "elite-fintech-web-legacy",
        "name": "Elite Fintech Web (retired duplicate)",
        "productionUrl": "https://elite-fintech-web-production.up.railway.app",
        "webhookPath": "/api/stripe/webhook",
        "merged": True,
        "projectSlug": "elite-fintech-web",
        "notes": "Retired duplicate — merged into elite-fintech-systems (Django API + React web monorepo)",
    },
    {
        "id": "api-transfer-legacy",
        "name": "API Transfer (retired)",
        "productionUrl": "https://api-transfer-production.up.railway.app",
        "webhookPath": "/api/billing/webhook",
        "merged": True,
        "notes": "Merged into automation-center — do not register",
    },
]


def catalog_by_slug(slug: str) -> CatalogEntry | None:
    for entry in PORTFOLIO_CATALOG:
        if entry.get("projectSlug") == slug:
            return entry
    return None


def catalog_live_urls(entry: CatalogEntry | None) -> dict[str, str]:
    """Railway-first live URLs — API vs web vs demo vs optional portfolio custom domain."""
    if not entry:
        return {}
    api = str(entry.get("productionUrl") or "").strip().rstrip("/")
    web = str(entry.get("webProductionUrl") or api).strip().rstrip("/")
    if entry.get("demoUrl"):
        demo = str(entry["demoUrl"]).strip().rstrip("/")
    elif web and web != api:
        demo = f"{web}/demo"
    else:
        demo = web
    portfolio = str(entry.get("portfolioDemoUrl") or "").strip().rstrip("/")
    return {
        "apiUrl": api,
        "webUrl": web,
        "demoUrl": demo,
        "portfolioDemoUrl": portfolio or demo,
    }


def is_stripe_exempt_slug(slug: str) -> bool:
    entry = catalog_by_slug(slug)
    if entry and entry.get("stripeExempt"):
        return True
    return slug in STRIPE_EXEMPT_SLUGS


def is_merged_legacy_slug(slug: str) -> bool:
    entry = catalog_by_slug(slug)
    if entry and entry.get("merged"):
        return True
    return slug in MERGED_LEGACY_PROJECT_SLUGS


def canonical_project_slug(slug: str) -> str:
    """Resolve merged legacy slugs to their canonical project."""
    return MERGED_INTO_PROJECT_SLUGS.get(slug, slug)


def stripe_billing_apps() -> list[CatalogEntry]:
    return [
        e
        for e in PORTFOLIO_CATALOG
        if not e.get("merged") and not e.get("stripeExempt") and e.get("productionUrl")
    ]


def catalog_summary() -> dict[str, Any]:
    active = [e for e in PORTFOLIO_CATALOG if not e.get("merged")]
    billing = stripe_billing_apps()
    exempt = [e for e in active if e.get("stripeExempt")]
    return {
        "totalApps": len(active),
        "stripeBillingCount": len(billing),
        "stripeExemptCount": len(exempt),
        "stripeExemptApps": [{"id": e["id"], "name": e["name"], "projectSlug": e.get("projectSlug")} for e in exempt],
        "stripeBillingApps": [{"id": e["id"], "name": e["name"], "projectSlug": e.get("projectSlug")} for e in billing],
        "mergedLegacySlugs": sorted(MERGED_LEGACY_PROJECT_SLUGS),
    }


def retired_webhook_urls() -> list[str]:
    """Stripe webhook URLs that must not be re-registered (merged/retired apps)."""
    urls: list[str] = []
    for entry in PORTFOLIO_CATALOG:
        if not entry.get("merged"):
            continue
        base = str(entry.get("productionUrl") or "").strip().rstrip("/")
        if not base:
            continue
        path = str(entry.get("webhookPath") or "/api/billing/webhook").strip()
        if not path.startswith("/"):
            path = f"/{path}"
        urls.append(f"{base}{path}")
    return list(dict.fromkeys(urls))


def retired_webhook_hosts() -> frozenset[str]:
    hosts: set[str] = set()
    for url in retired_webhook_urls():
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").strip().lower()
        if host:
            hosts.add(host)
    return frozenset(hosts)
