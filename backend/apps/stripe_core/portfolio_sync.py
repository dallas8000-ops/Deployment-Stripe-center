"""Sync portfolio registry from catalog + project workspace paths."""

from __future__ import annotations

from typing import Any

from apps.projects.models import Project

from .portfolio_catalog import PORTFOLIO_CATALOG, catalog_summary, is_merged_legacy_slug
from .portfolio_paths import portfolio_registry_path
from .portfolio_registry import PortfolioApp, ensure_registry_template, save_registry


def catalog_entry_to_app(entry: dict[str, Any], *, local_path: str = "") -> PortfolioApp:
    return PortfolioApp(
        id=str(entry["id"]),
        name=str(entry["name"]),
        production_url=str(entry.get("productionUrl") or "").rstrip("/"),
        webhook_path=str(entry.get("webhookPath") or "/stripe/webhook"),
        health_path=str(entry.get("healthPath") or "/health/"),
        project_slug=str(entry.get("projectSlug") or ""),
        local_path=local_path,
        stripe_exempt=bool(entry.get("stripeExempt")),
        notes=str(entry.get("notes") or ""),
    )


def sync_portfolio_registry(projects: list[Project] | None = None) -> dict[str, Any]:
    """Write ~/.stripe-installer/portfolio-registry.json from the canonical catalog."""
    by_slug = {p.slug: p for p in (projects or [])}
    ensure_registry_template()

    apps: list[PortfolioApp] = []
    for raw in PORTFOLIO_CATALOG:
        if raw.get("merged"):
            continue
        slug = str(raw.get("projectSlug") or "")
        project = by_slug.get(slug)
        local_path = project.local_path if project and project.local_path else ""
        apps.append(catalog_entry_to_app(raw, local_path=local_path))

    path = save_registry(apps)
    summary = catalog_summary()
    return {
        "registryPath": str(path),
        "appCount": len(apps),
        "portfolioSummary": summary,
    }
