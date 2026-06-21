"""Canonical Gilliom portfolio apps — Stripe billing vs exempt storefronts/APIs."""

from __future__ import annotations

from typing import Any, TypedDict


class CatalogEntry(TypedDict, total=False):
    id: str
    name: str
    productionUrl: str
    webhookPath: str
    healthPath: str
    projectSlug: str
    stripeExempt: bool
    merged: bool
    notes: str


# Slugs hidden from the Projects dashboard (merged into Automation Center).
MERGED_LEGACY_PROJECT_SLUGS: frozenset[str] = frozenset(
    {
        "api-transfer",
        "api_transfer",
    }
)

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
        "name": "Elite Fintech Web",
        "productionUrl": "https://elite-fintech-web-production.up.railway.app",
        "webhookPath": "/api/stripe/webhook",
        "healthPath": "/health/",
        "projectSlug": "elite-fintech-web",
    },
    {
        "id": "kistie-store",
        "name": "Kistie Store",
        "productionUrl": "https://kistie-store-production.up.railway.app",
        "healthPath": "/health/",
        "projectSlug": "kistie-store",
        "stripeExempt": True,
        "notes": "Portfolio exempt — no Stripe subscription billing",
    },
    {
        "id": "silverfox",
        "name": "SilverFox",
        "productionUrl": "https://silverfox-production.up.railway.app",
        "healthPath": "/health/",
        "projectSlug": "silverfox",
        "stripeExempt": True,
        "notes": "Men's fashion e-commerce — Django SSR, live FX, Stripe checkout planned",
    },
    {
        "id": "blog-api",
        "name": "Django REST Blog API",
        "productionUrl": "https://blog-2-production-72bc.up.railway.app",
        "healthPath": "/health/",
        "projectSlug": "blog-2",
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
        "notes": "Webhook on API service (not dbops-web frontend)",
    },
    {
        "id": "specwright",
        "name": "Specwright",
        "productionUrl": "https://specwright-api-production.up.railway.app",
        "webhookPath": "/api/v1/billing/webhook/",
        "healthPath": "/health/",
        "projectSlug": "specwright",
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
