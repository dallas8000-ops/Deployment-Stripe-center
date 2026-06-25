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


def _service_public_hosts(token: str, project_id: str, service_id: str) -> set[str]:
    try:
        projects = _list_railway_projects_with_domains(token)
    except RuntimeError:
        return set()
    for proj in projects:
        if proj.get("id") != project_id:
            continue
        for svc in proj.get("services") or []:
            if svc.get("id") != service_id:
                continue
            return {str(d).strip().lower() for d in svc.get("domains") or [] if str(d).strip()}
    return set()


def _railway_ids_trusted_for_catalog(
    project: Project, token: str, project_id: str, service_id: str
) -> bool:
    """True when stored Railway IDs serve this project's catalog production hostname."""
    catalog_host = _catalog_production_host(project)
    if not catalog_host:
        return True
    hosts = _service_public_hosts(token, project_id, service_id)
    if not hosts:
        return False
    return catalog_host in hosts or any(
        catalog_host == host or catalog_host in host or host in catalog_host for host in hosts
    )


def ensure_railway_targets_detected(project: Project, token: str | None = None) -> dict[str, Any]:
    """
    Detect Railway project + web service from catalog hostname, name, or slug.
    Re-resolves when vault IDs point at a different app's service.
    """
    resolved_token = (token or get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
    if not resolved_token:
        from apps.stripe_core.hub_keys import HUB_SLUG, get_hub_project

        if project.slug != HUB_SLUG:
            hub = get_hub_project(project.owner)
            if hub:
                resolved_token = (get_secret(hub, "RAILWAY_API_TOKEN") or "").strip()
    if not resolved_token:
        scan = project.scan_data or {}
        railway = scan.get("railway") or {}
        return {
            "detected": False,
            "projectId": get_secret(project, "RAILWAY_PROJECT_ID") or railway.get("projectId"),
            "serviceId": get_secret(project, "RAILWAY_SERVICE_ID") or railway.get("serviceId"),
            "message": "Add RAILWAY_API_TOKEN to hub vault to auto-detect Railway targets",
        }

    stored_pid = (get_secret(project, "RAILWAY_PROJECT_ID") or "").strip()
    stored_sid = (get_secret(project, "RAILWAY_SERVICE_ID") or "").strip()
    if (
        stored_pid
        and stored_sid
        and _railway_ids_trusted_for_catalog(project, resolved_token, stored_pid, stored_sid)
    ):
        return {
            "detected": False,
            "projectId": stored_pid,
            "serviceId": stored_sid,
            "message": "Railway targets match portfolio catalog",
        }

    project_id = resolve_railway_project_id(project, resolved_token)
    if not project_id:
        return {
            "detected": False,
            "projectId": stored_pid or None,
            "serviceId": stored_sid or None,
            "message": "Could not match Railway project — check token scope or save RAILWAY_PROJECT_ID",
        }
    service_id = resolve_railway_web_service_id(project, resolved_token, project_id)
    if not service_id:
        return {
            "detected": False,
            "projectId": project_id,
            "serviceId": None,
            "message": "Railway project found but web service could not be matched",
        }

    remember_railway_targets(project, project_id, service_id, overwrite=True)
    sync_production_url_from_railway(project, resolved_token, project_id, service_id)
    return {
        "detected": True,
        "projectId": project_id,
        "serviceId": service_id,
        "message": "Detected Railway project/service from portfolio catalog + Railway API",
    }


def resolve_railway_project_id(project: Project, token: str) -> str | None:
    stored = (get_secret(project, "RAILWAY_PROJECT_ID") or "").strip()
    service_stored = (get_secret(project, "RAILWAY_SERVICE_ID") or "").strip()
    if stored and (
        not _catalog_production_host(project)
        or (
            service_stored
            and _railway_ids_trusted_for_catalog(project, token, stored, service_stored)
        )
    ):
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
    if stored and _railway_ids_trusted_for_catalog(project, token, project_id, stored):
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


def sync_production_url_from_railway(
    project: Project,
    token: str,
    project_id: str,
    service_id: str,
) -> str | None:
    """Set productionUrl from Railway public domain when still localhost or empty."""
    scan = project.scan_data or {}
    current = str(scan.get("productionUrl") or scan.get("production_url") or "").strip()
    if current and not current.startswith("http://127.0.0.1") and "localhost" not in current:
        return current

    try:
        projects = _list_railway_projects_with_domains(token)
    except RuntimeError:
        return None

    for proj in projects:
        if proj.get("id") != project_id:
            continue
        for svc in proj.get("services") or []:
            if svc.get("id") != service_id:
                continue
            domains = svc.get("domains") or []
            if not domains:
                return None
            url = f"https://{domains[0].lstrip('https://').lstrip('http://')}"
            update_project_scan_data(
                project,
                {"productionUrl": url, "production_url": url},
            )
            return url
    return None


def remember_railway_targets(
    project: Project, project_id: str, service_id: str, *, overwrite: bool = False
) -> None:
    update_project_scan_data(
        project,
        {"railway": {"projectId": project_id, "serviceId": service_id}},
    )

    if overwrite or not get_secret(project, "RAILWAY_PROJECT_ID"):
        set_secret(project, "RAILWAY_PROJECT_ID", project_id)
    if overwrite or not get_secret(project, "RAILWAY_SERVICE_ID"):
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
