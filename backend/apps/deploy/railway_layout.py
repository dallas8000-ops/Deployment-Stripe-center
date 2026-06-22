"""Canonical Railway service names for portfolio monorepos (single shared project)."""

from __future__ import annotations

from typing import Any, TypedDict


class RailwayServiceSpec(TypedDict):
    name: str
    aliases: tuple[str, ...]
    root_directory: str
    dockerfile_path: str
    role: str


class RailwayAppLayout(TypedDict):
    app_label: str
    api_host: str
    web_host: str
    services: tuple[RailwayServiceSpec, ...]


ELITE_FINTECH_RAILWAY: RailwayAppLayout = {
    "app_label": "Elite Fintech Systems",
    "api_host": "elite-fintech-api-production.up.railway.app",
    "web_host": "elite-fintech-web-production.up.railway.app",
    "services": (
        {
            "name": "elite-fintech-systems-api",
            "aliases": ("elite-fintech-api", "Elite-Fintech-API", "elite-fintech-api-production"),
            "root_directory": "apps/backend",
            "dockerfile_path": "Dockerfile",
            "role": "api",
        },
        {
            "name": "elite-fintech-systems-web",
            "aliases": ("Elite-Fintech-Web", "elite-fintech-web", "elite-fintech-web-production"),
            "root_directory": ".",
            "dockerfile_path": "apps/web/Dockerfile",
            "role": "web",
        },
        {
            "name": "elite-fintech-systems-db",
            "aliases": ("Postgres-Fintech", "postgres-fintech"),
            "root_directory": "",
            "dockerfile_path": "",
            "role": "database",
        },
    ),
}

PORTFOLIO_RAILWAY_LAYOUTS: dict[str, RailwayAppLayout] = {
    "elite-fintech-systems": ELITE_FINTECH_RAILWAY,
}


def layout_for_slug(slug: str) -> RailwayAppLayout | None:
    return PORTFOLIO_RAILWAY_LAYOUTS.get((slug or "").strip().lower())


def _norm(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def service_matches(spec: RailwayServiceSpec, service_name: str, domains: list[str], layout: RailwayAppLayout) -> bool:
    name = (service_name or "").strip()
    norm_name = _norm(name)
    for alias in (spec["name"],) + spec["aliases"]:
        if _norm(alias) == norm_name:
            return True
    if spec["role"] == "api" and layout["api_host"] in domains:
        return True
    if spec["role"] == "web" and layout["web_host"] in domains:
        return True
    if spec["role"] == "database" and "postgres" in name.lower() and "fintech" in name.lower():
        return True
    return False


def audit_report(
    layout: RailwayAppLayout,
    projects: list[dict[str, Any]],
) -> dict[str, Any]:
    """Match live Railway services to canonical names within any project."""
    matched: dict[str, dict[str, Any]] = {}
    project_hits: list[dict[str, Any]] = []

    for proj in projects:
        proj_services = proj.get("services") or []
        hits = 0
        for svc in proj_services:
            domains = svc.get("domains") or []
            for spec in layout["services"]:
                if service_matches(spec, svc.get("name") or "", domains, layout):
                    matched[spec["name"]] = {
                        "current_name": svc.get("name"),
                        "service_id": svc.get("id"),
                        "project_id": proj.get("id"),
                        "project_name": proj.get("name"),
                        "domains": domains,
                        "role": spec["role"],
                        "target_name": spec["name"],
                        "needs_rename": (svc.get("name") or "") != spec["name"],
                    }
                    hits += 1
        if hits:
            project_hits.append(
                {
                    "id": proj.get("id"),
                    "name": proj.get("name"),
                    "service_count": len(proj_services),
                    "elite_hits": hits,
                }
            )

    home = project_hits[0] if len(project_hits) == 1 else None
    return {
        "layout": layout,
        "matched": matched,
        "project_hits": project_hits,
        "home_project": home,
        "missing": [s["name"] for s in layout["services"] if s["name"] not in matched],
        "split_across_projects": len(project_hits) > 1,
    }
