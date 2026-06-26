"""Audit which portfolio apps live inside the shared hearty-enjoyment Railway project."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from apps.deploy.railway_resolve import _list_railway_projects_with_domains
from apps.stripe_core.portfolio_catalog import PORTFOLIO_LIVE_URLS, PORTFOLIO_LIVE_URL_SLUGS, catalog_by_slug

RAILWAY_HOME_PROJECT_NAME = "hearty-enjoyment"
RAILWAY_HOME_PROJECT_ID = "e5dce2f2-ffc6-4677-8f16-d3912934cebd"

# Standalone Railway projects that are allowed outside hearty-enjoyment (for now).
ALLOWED_STANDALONE_PROJECTS = frozenset(
    {
        "hearty-enjoyment",
        # AgriPay still has its own project until consolidate_railway_monorepo --confirm runs.
        "agripay-logistics-ai",
    }
)


def _host_project_map(projects: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Map public Railway hostname → {projectId, projectName, serviceName}."""
    mapping: dict[str, dict[str, str]] = {}
    for proj in projects:
        project_name = str(proj.get("name") or "")
        project_id = str(proj.get("id") or "")
        for svc in proj.get("services") or []:
            service_name = str(svc.get("name") or "")
            for domain in svc.get("domains") or []:
                host = domain.strip().lower()
                if host:
                    mapping[host] = {
                        "projectId": project_id,
                        "projectName": project_name,
                        "serviceName": service_name,
                    }
    return mapping


def audit_railway_home_layout(token: str) -> dict[str, Any]:
    """
    Report portfolio URL placement vs hearty-enjoyment.
    Does not move services — use consolidate_railway_monorepo for AgriPay migration.
    """
    projects = _list_railway_projects_with_domains(token)
    host_map = _host_project_map(projects)

    home = next(
        (p for p in projects if (p.get("name") or "").lower() == RAILWAY_HOME_PROJECT_NAME.lower()),
        None,
    )
    home_services = sorted(
        (s.get("name") or "?" for s in (home or {}).get("services") or []),
        key=str.lower,
    )

    app_rows: list[dict[str, Any]] = []
    outside_home: list[dict[str, Any]] = []

    for link_id, url in PORTFOLIO_LIVE_URLS.items():
        if link_id in ("marketingSite",):
            continue
        host = (urlparse(url).hostname or "").lower()
        if not host:
            continue
        slug = PORTFOLIO_LIVE_URL_SLUGS.get(link_id, "")
        entry = catalog_by_slug(slug) if slug else None
        placement = host_map.get(host)
        if not placement:
            # Try prefix match for railway default domains
            for mapped_host, info in host_map.items():
                if host in mapped_host or mapped_host in host:
                    placement = info
                    break

        in_home = bool(
            placement
            and (
                placement.get("projectId") == RAILWAY_HOME_PROJECT_ID
                or (placement.get("projectName") or "").lower() == RAILWAY_HOME_PROJECT_NAME.lower()
            )
        )
        row = {
            "linkId": link_id,
            "projectSlug": slug,
            "name": (entry or {}).get("name") or link_id,
            "url": url,
            "host": host,
            "railwayProject": (placement or {}).get("projectName") or "(not found)",
            "railwayService": (placement or {}).get("serviceName") or "",
            "inHeartyEnjoyment": in_home,
        }
        app_rows.append(row)
        if placement and not in_home:
            outside_home.append(row)

    other_projects = [
        {"name": p.get("name"), "id": p.get("id"), "serviceCount": len(p.get("services") or [])}
        for p in projects
        if (p.get("name") or "").lower() not in {n.lower() for n in ALLOWED_STANDALONE_PROJECTS}
    ]

    return {
        "homeProject": {
            "name": RAILWAY_HOME_PROJECT_NAME,
            "id": RAILWAY_HOME_PROJECT_ID,
            "serviceCount": len(home_services),
            "services": home_services,
        },
        "apps": app_rows,
        "outsideHeartyEnjoyment": outside_home,
        "extraRailwayProjects": other_projects,
        "summary": {
            "appsInHome": sum(1 for r in app_rows if r["inHeartyEnjoyment"]),
            "appsOutsideHome": len(outside_home),
            "extraProjects": len(other_projects),
        },
    }
