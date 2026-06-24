"""Resolve Railway project + web service IDs for automatic env push."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from apps.projects.models import Project
from apps.projects.scan_data_utils import update_project_scan_data
from apps.stripe_core.portfolio_catalog import catalog_by_slug
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
    if catalog and catalog.get("productionUrl"):
        host = (urlparse(str(catalog["productionUrl"])).hostname or "").lower()
        if host:
            prefix = host.split(".")[0]
            for variant in (host, prefix, prefix.replace("-production", "")):
                if variant and variant not in names:
                    names.append(variant)
    return names


def _catalog_production_host(project: Project) -> str:
    catalog = catalog_by_slug(project.slug or "")
    if not catalog:
        return ""
    return (urlparse(str(catalog.get("productionUrl") or "")).hostname or "").lower()


def _list_railway_projects_with_domains(token: str) -> list[dict[str, Any]]:
    """Projects with services and public domains — for matching portfolio production URLs."""
    data = _railway_gql(
        token,
        """
        query {
          projects {
            edges {
              node {
                id
                name
                services {
                  edges {
                    node {
                      id
                      name
                      serviceInstances {
                        edges {
                          node {
                            domains {
                              serviceDomains {
                                domain
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
    )
    rows: list[dict[str, Any]] = []
    for edge in (data.get("projects") or {}).get("edges", []):
        node = edge.get("node") or {}
        project_id = str(node.get("id") or "").strip()
        if not project_id:
            continue
        services: list[dict[str, str]] = []
        for svc_edge in (node.get("services") or {}).get("edges", []):
            svc = svc_edge.get("node") or {}
            service_id = str(svc.get("id") or "").strip()
            name = str(svc.get("name") or "").strip()
            domains: list[str] = []
            for inst_edge in (svc.get("serviceInstances") or {}).get("edges", []):
                inst = inst_edge.get("node") or {}
                dom_block = inst.get("domains") or {}
                for dom in dom_block.get("serviceDomains") or []:
                    if isinstance(dom, dict):
                        domain = str(dom.get("domain") or dom.get("host") or "").strip().lower()
                    else:
                        domain = str(dom).strip().lower()
                    if domain:
                        domains.append(domain)
            if service_id:
                services.append({"id": service_id, "name": name, "domains": domains})
        rows.append({"id": project_id, "name": str(node.get("name") or ""), "services": services})
    return rows


def resolve_railway_targets_by_domain(project: Project, token: str) -> tuple[str | None, str | None]:
    """Match catalog productionUrl hostname to a Railway service domain."""
    target_host = _catalog_production_host(project)
    return resolve_railway_service_by_host(token, target_host)


def resolve_railway_service_by_host(token: str, target_host: str) -> tuple[str | None, str | None]:
    """Match a Railway public hostname to project + service IDs."""
    target_host = (target_host or "").strip().lower()
    if not target_host:
        return None, None
    try:
        projects = _list_railway_projects_with_domains(token)
    except RuntimeError:
        return None, None
    for proj in projects:
        for svc in proj.get("services") or []:
            if "postgres" in (svc.get("name") or "").lower():
                continue
            for domain in svc.get("domains") or []:
                if domain == target_host or domain.startswith(target_host.split(".")[0]):
                    return proj["id"], svc["id"]
            if target_host.endswith(".up.railway.app") and any(
                target_host in d or d in target_host for d in svc.get("domains") or []
            ):
                return proj["id"], svc["id"]
    return None, None


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
    project_id, _service_id = resolve_railway_targets_by_domain(project, token)
    if project_id:
        return project_id
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

    _project_id, service_id = resolve_railway_targets_by_domain(project, token)
    if service_id and _project_id == project_id:
        return service_id
    return None


def remember_railway_targets(project: Project, project_id: str, service_id: str) -> None:
    update_project_scan_data(
        project,
        {"railway": {"projectId": project_id, "serviceId": service_id}},
    )

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
