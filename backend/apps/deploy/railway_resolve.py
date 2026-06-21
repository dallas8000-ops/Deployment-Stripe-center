"""Resolve Railway project + web service IDs for automatic env push."""

from __future__ import annotations

import re
from typing import Any

from apps.projects.models import Project
from apps.stripe_installer.portfolio_catalog import catalog_by_slug
from apps.vault.models import get_secret, set_secret

from .env_push import ENV_PRESETS, _railway_gql
from .provision import _sanitize_name


def preset_for_project(project: Project) -> str | None:
    slug = (project.slug or "").strip().lower()
    aliases = {
        "kistie_store": "kistie-store",
        "kistie": "kistie-store",
    }
    preset = aliases.get(slug, slug)
    return preset if preset in ENV_PRESETS else None


def _railway_project_candidates(project: Project) -> list[str]:
    catalog = catalog_by_slug(project.slug or "")
    names: list[str] = []
    for value in (
        project.name,
        project.slug,
        (catalog or {}).get("name"),
        (catalog or {}).get("projectSlug"),
    ):
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)
    slug = (project.slug or project.name or "").strip()
    if slug:
        dashed = slug.replace("_", "-")
        spaced = re.sub(r"[-_]+", " ", slug).title()
        for variant in (dashed, spaced, slug.title()):
            if variant not in names:
                names.append(variant)
    return names


def _list_railway_projects(token: str) -> list[dict[str, str]]:
    data = _railway_gql(token, "query { projects { edges { node { id name } } } }")
    projects: list[dict[str, str]] = []
    for edge in (data.get("projects") or {}).get("edges", []):
        node = edge.get("node") or {}
        project_id = str(node.get("id") or "").strip()
        name = str(node.get("name") or "").strip()
        if project_id:
            projects.append({"id": project_id, "name": name})
    return projects


def _list_railway_services(token: str, project_id: str) -> list[dict[str, str]]:
    data = _railway_gql(
        token,
        """
        query($id: String!) {
          project(id: $id) {
            services { edges { node { id name } } }
          }
        }
        """,
        {"id": project_id},
    )
    services: list[dict[str, str]] = []
    for edge in ((data.get("project") or {}).get("services") or {}).get("edges", []):
        node = edge.get("node") or {}
        service_id = str(node.get("id") or "").strip()
        name = str(node.get("name") or "").strip()
        if service_id:
            services.append({"id": service_id, "name": name})
    return services


def _name_matches(candidate: str, target: str) -> bool:
    left = re.sub(r"[^a-z0-9]+", "", candidate.lower())
    right = re.sub(r"[^a-z0-9]+", "", target.lower())
    return bool(left and right and left == right)


def resolve_railway_project_id(project: Project, token: str) -> str | None:
    stored = (get_secret(project, "RAILWAY_PROJECT_ID") or "").strip()
    if stored:
        return stored

    scan = project.scan_data or {}
    for key in ("railway", "postgres"):
        block = scan.get(key) or {}
        if isinstance(block, dict):
            project_id = str(block.get("projectId") or "").strip()
            if project_id:
                return project_id

    safe_slug = _sanitize_name(project.slug or project.name or "")
    candidates = _railway_project_candidates(project)
    for item in _list_railway_projects(token):
        name = item["name"]
        if name in candidates:
            return item["id"]
        if _sanitize_name(name) == safe_slug:
            return item["id"]
        if any(_name_matches(name, candidate) for candidate in candidates):
            return item["id"]
    return None


def resolve_railway_web_service_id(project: Project, token: str, project_id: str) -> str | None:
    stored = (get_secret(project, "RAILWAY_SERVICE_ID") or "").strip()
    if stored:
        return stored

    scan = project.scan_data or {}
    railway = scan.get("railway") or {}
    if isinstance(railway, dict):
        service_id = str(railway.get("serviceId") or "").strip()
        if service_id:
            return service_id

    services = _list_railway_services(token, project_id)
    web_services = [
        s for s in services if "postgres" not in (s.get("name") or "").lower()
    ]
    if not web_services:
        return None

    candidates = _railway_project_candidates(project)
    for service in web_services:
        name = service.get("name") or ""
        if name in candidates:
            return service["id"]
        if any(_name_matches(name, candidate) for candidate in candidates):
            return service["id"]

    if len(web_services) == 1:
        return web_services[0]["id"]
    return None


def remember_railway_targets(project: Project, project_id: str, service_id: str) -> None:
    scan = dict(project.scan_data or {})
    railway = dict(scan.get("railway") or {})
    railway["projectId"] = project_id
    railway["serviceId"] = service_id
    scan["railway"] = railway
    project.scan_data = scan
    project.save(update_fields=["scan_data", "updated_at"])

    if not get_secret(project, "RAILWAY_PROJECT_ID"):
        set_secret(project, "RAILWAY_PROJECT_ID", project_id)
    if not get_secret(project, "RAILWAY_SERVICE_ID"):
        set_secret(project, "RAILWAY_SERVICE_ID", service_id)


def railway_env_push_status(project: Project) -> dict[str, Any]:
    preset = preset_for_project(project)
    token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
    scan = project.scan_data or {}
    railway = scan.get("railway") or {}
    return {
        "preset": preset,
        "hasToken": bool(token),
        "projectId": get_secret(project, "RAILWAY_PROJECT_ID") or railway.get("projectId"),
        "serviceId": get_secret(project, "RAILWAY_SERVICE_ID") or railway.get("serviceId"),
        "lastEnvPushAt": railway.get("lastEnvPushAt"),
        "lastPushedKeys": railway.get("lastPushedKeys") or [],
    }
