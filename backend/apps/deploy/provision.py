"""Neon / Supabase / Railway / self-hosted postgres provision."""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Literal

from apps.projects.models import Project
from apps.vault.models import get_secret, set_secret

from .postgres import apply_postgres_schema, test_postgres_connection
from .railway_client import railway_gql

Provider = Literal["neon", "supabase", "railway", "self-hosted"]
NEON_API = "https://console.neon.tech/api/v2"
SUPABASE_API = "https://api.supabase.com/v1"


def _sanitize_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9-]", "-", name.lower())
    return re.sub(r"-+", "-", s)[:48]


def _http_json(method: str, url: str, headers: dict, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _neon_request(api_key: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    return _http_json(
        method,
        f"{NEON_API}{path}",
        {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body,
    )


def _supabase_request(token: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    return _http_json(
        method,
        f"{SUPABASE_API}{path}",
        {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        body,
    )


def _provision_neon(project: Project, region: str, reuse: bool) -> tuple[str, str, bool]:
    api_key = get_secret(project, "NEON_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NEON_API_KEY not in vault — store at https://console.neon.tech/app/settings/api-keys"
        )
    safe = _sanitize_name(project.slug or project.name)

    if reuse:
        listed = _neon_request(api_key, "/projects")
        for item in listed.get("projects", []):
            if item.get("name") == safe:
                pid = item["id"]
                uri = _neon_request(
                    api_key,
                    f"/projects/{pid}/connection_uri?database_name=neondb&role_name=neondb_owner&pooled=true",
                )
                return uri["uri"], pid, True

    created = _neon_request(
        api_key,
        "/projects",
        "POST",
        {"project": {"name": safe, "region_id": region, "pg_version": 16}},
    )
    pid = created["project"]["id"]
    uris = created.get("connection_uris") or []
    if uris:
        return uris[0]["connection_uri"], pid, False
    uri = _neon_request(
        api_key,
        f"/projects/{pid}/connection_uri?database_name=neondb&role_name=neondb_owner&pooled=true",
    )
    return uri["uri"], pid, False


def _wait_supabase_healthy(token: str, ref: str) -> None:
    for _ in range(30):
        proj = _supabase_request(token, f"/projects/{ref}")
        if proj.get("status") == "ACTIVE_HEALTHY":
            return
        time.sleep(4)
    raise RuntimeError("Supabase project did not become healthy in time")


def _provision_supabase(project: Project, region: str, reuse: bool) -> tuple[str, str, bool]:
    token = get_secret(project, "SUPABASE_ACCESS_TOKEN")
    org_id = get_secret(project, "SUPABASE_ORG_ID")
    if not token:
        raise RuntimeError("SUPABASE_ACCESS_TOKEN not in vault")
    if not org_id:
        raise RuntimeError("SUPABASE_ORG_ID not in vault")
    safe = _sanitize_name(project.slug or project.name)

    if reuse:
        projects = _supabase_request(token, "/projects")
        if isinstance(projects, list):
            for item in projects:
                if item.get("name") == safe:
                    ref = item["id"]
                    db_pass = get_secret(project, "SUPABASE_DB_PASSWORD")
                    if not db_pass:
                        raise RuntimeError("SUPABASE_DB_PASSWORD missing for existing project")
                    url = (
                        f"postgresql://postgres:{urllib.parse.quote(db_pass)}"
                        f"@db.{ref}.supabase.co:5432/postgres?sslmode=require"
                    )
                    return url, ref, True

    db_pass = secrets.token_urlsafe(24)
    created = _supabase_request(
        token,
        "/projects",
        "POST",
        {"organization_id": org_id, "name": safe, "region": region, "db_pass": db_pass},
    )
    ref = created["id"]
    _wait_supabase_healthy(token, ref)
    set_secret(project, "SUPABASE_DB_PASSWORD", db_pass)
    url = (
        f"postgresql://postgres:{urllib.parse.quote(db_pass)}"
        f"@db.{ref}.supabase.co:5432/postgres?sslmode=require"
    )
    return url, ref, False


def _railway_graphql(token: str, query: str, variables: dict | None = None) -> dict:
    data = railway_gql(token, query, variables)
    return {"data": data}


def _railway_get_database_url(token: str, project_id: str) -> str | None:
    data = _railway_graphql(
        token,
        """
        query($id: String!) {
          project(id: $id) {
            services { edges { node { id name serviceInstances { edges { node {
              latestDeployment { meta } } } } } } }
          }
        }
        """,
        {"id": project_id},
    )
    project = data.get("data", {}).get("project") or {}
    postgres_service_id: str | None = None
    for edge in project.get("services", {}).get("edges", []):
        node = edge.get("node") or {}
        if "postgres" in (node.get("name") or "").lower():
            postgres_service_id = node.get("id")
            for inst in node.get("serviceInstances", {}).get("edges", []):
                meta = (inst.get("node") or {}).get("latestDeployment", {}).get("meta") or {}
                for key in ("DATABASE_URL", "DATABASE_PRIVATE_URL", "POSTGRES_URL"):
                    if meta.get(key):
                        return meta[key]

    if not postgres_service_id:
        return None

    from .env_push import _railway_environment_id

    try:
        env_id = _railway_environment_id(token, project_id)
        vars_payload = _railway_graphql(
            token,
            """
            query($projectId: String!, $environmentId: String!, $serviceId: String!) {
              variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
            }
            """,
            {
                "projectId": project_id,
                "environmentId": env_id,
                "serviceId": postgres_service_id,
            },
        )
        variables = (vars_payload.get("data") or {}).get("variables") or {}
        if isinstance(variables, str):
            variables = json.loads(variables)
        for key in ("DATABASE_URL", "DATABASE_PRIVATE_URL", "POSTGRES_URL", "DATABASE_PUBLIC_URL"):
            value = variables.get(key) if isinstance(variables, dict) else None
            if value:
                return value
    except RuntimeError:
        pass
    return None


def _railway_cli_available() -> bool:
    return shutil.which("railway") is not None


def _railway_project_matches(node_name: str, safe: str, project: Project) -> bool:
    from apps.deploy.railway_resolve import _name_matches, _railway_project_candidates

    name = str(node_name or "").strip()
    if not name:
        return False
    if name == safe or _sanitize_name(name) == safe:
        return True
    candidates = _railway_project_candidates(project)
    if name in candidates:
        return True
    return any(_name_matches(name, candidate) for candidate in candidates)


def _provision_railway_api(project: Project, safe: str, reuse: bool, token: str) -> tuple[str, str, bool]:
    matched_id: str | None = None
    if reuse:
        listed = _railway_graphql(
            token,
            "query { projects { edges { node { id name } } } }",
        )
        for edge in listed.get("data", {}).get("projects", {}).get("edges", []):
            node = edge["node"]
            if _railway_project_matches(node.get("name") or "", safe, project):
                matched_id = node["id"]
                url = _railway_get_database_url(token, node["id"])
                if url:
                    return url, node["id"], True

    if reuse and matched_id:
        for _ in range(15):
            url = _railway_get_database_url(token, matched_id)
            if url:
                return url, matched_id, True
            time.sleep(4)
        raise RuntimeError(
            "Found Railway project but Postgres DATABASE_URL is not available via API. "
            "Add a Postgres plugin in the Railway dashboard — SilverFox env preset uses "
            "${{Postgres.DATABASE_URL}} at deploy time."
        )

    created = _railway_graphql(
        token,
        "mutation($name: String!) { projectCreate(input: { name: $name }) { project { id } } }",
        {"name": safe},
    )
    project_id = created["data"]["projectCreate"]["project"]["id"]
    _railway_graphql(
        token,
        """
        mutation($projectId: String!) {
          serviceCreate(input: {
            projectId: $projectId
            name: "Postgres"
            source: { image: "postgres:16-alpine" }
          }) { service { id } }
        }
        """,
        {"projectId": project_id},
    )
    for _ in range(45):
        url = _railway_get_database_url(token, project_id)
        if url:
            return url, project_id, False
        time.sleep(4)
    raise RuntimeError("Railway Postgres URL not available — check Railway dashboard")


def _provision_railway_cli(project: Project, safe: str, token: str) -> tuple[str, str, bool]:
    env = {**os.environ, "RAILWAY_TOKEN": token}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        login = subprocess.run(
            ["railway", "login", "--token", token],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
        )
        if login.returncode != 0:
            raise RuntimeError(login.stderr or login.stdout or "railway login failed")
        subprocess.run(
            ["railway", "init", "--name", safe],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["railway", "add", "-d", "postgres"],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        vars_out = subprocess.run(
            ["railway", "variables", "--json"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        variables = json.loads(vars_out.stdout)
        url = variables.get("DATABASE_URL") or variables.get("DATABASE_PRIVATE_URL")
        if not url:
            raise RuntimeError("Railway CLI did not return DATABASE_URL")

        listed = _railway_graphql(
            token,
            "query { projects { edges { node { id name } } } }",
        )
        project_id: str | None = None
        for edge in listed.get("data", {}).get("projects", {}).get("edges", []):
            node = edge.get("node") or {}
            if _railway_project_matches(node.get("name") or "", safe, project):
                project_id = node.get("id")
                break
        if not project_id:
            raise RuntimeError(
                "Railway CLI provision succeeded but project ID could not be resolved — "
                "add RAILWAY_PROJECT_ID to vault manually"
            )
        return url, project_id, False


def _provision_railway(project: Project, region: str, reuse: bool) -> tuple[str, str, bool]:
    token = get_secret(project, "RAILWAY_API_TOKEN")
    if not token:
        raise RuntimeError("RAILWAY_API_TOKEN not in vault — https://railway.com/account/tokens")
    safe = _sanitize_name(project.slug or project.name)
    if _railway_cli_available():
        try:
            return _provision_railway_cli(project, safe, token)
        except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError, OSError):
            pass
    return _provision_railway_api(project, safe, reuse, token)


def _provision_self_hosted(project: Project) -> tuple[str, str, bool]:
    url = get_secret(project, "DATABASE_URL")
    if not url or not url.startswith(("postgres://", "postgresql://")):
        raise RuntimeError("For self-hosted, store a valid DATABASE_URL in vault first")
    conn = test_postgres_connection(url)
    if not conn["ok"]:
        raise RuntimeError(f"Self-hosted DATABASE_URL failed: {conn['message']}")
    return url, "self-hosted", True


def should_skip_external_postgres_for_railway(
    project: Project,
    platform: str,
    provider: str,
) -> bool:
    """
    Railway-hosted apps with a Postgres plugin should use ${{Postgres.DATABASE_URL}}
    via env push — not Neon/Supabase provisioning or legacy Railway serviceCreate API.
    """
    if platform != "railway":
        return False

    from apps.deploy.env_push import ENV_PRESETS, is_railway_reference
    from apps.deploy.railway_resolve import preset_for_project

    existing = (get_secret(project, "DATABASE_URL") or "").strip()
    if existing and is_railway_reference(existing):
        return True

    if provider == "railway":
        return True

    preset = preset_for_project(project)
    preset_db = (ENV_PRESETS.get(preset or "") or {}).get("DATABASE_URL", "")
    if preset_db.startswith("${{"):
        return True
    if provider == "neon" and not get_secret(project, "NEON_API_KEY"):
        return True
    return False


def provision_postgres(
    project: Project,
    provider: Provider = "neon",
    region: str | None = None,
    reuse: bool = True,
    apply_schema: bool = True,
) -> dict:
    from apps.deploy.env_push import is_railway_reference

    existing = (get_secret(project, "DATABASE_URL") or "").strip()
    if existing and reuse and is_railway_reference(existing):
        return {
            "provider": provider,
            "stored": True,
            "reused": True,
            "message": (
                "Using Railway Postgres reference in vault — "
                "DATABASE_URL is resolved on Railway at deploy time"
            ),
        }
    if existing and reuse and existing.startswith(("postgres://", "postgresql://")):
        result = {
            "provider": provider,
            "stored": True,
            "reused": True,
            "message": "Using existing DATABASE_URL from vault",
        }
        if apply_schema:
            schema = apply_postgres_schema(project)
            result["schema"] = schema
            if schema["ok"]:
                result["message"] += " — schema applied"
        return result

    if provider == "neon":
        region = region or "aws-us-east-1"
        url, project_id, reused = _provision_neon(project, region, reuse)
        manifest = {"provider": "neon", "projectId": project_id, "reused": reused}
    elif provider == "supabase":
        region = region or "us-east-1"
        url, project_ref, reused = _provision_supabase(project, region, reuse)
        manifest = {"provider": "supabase", "projectRef": project_ref, "reused": reused}
    elif provider == "railway":
        url, project_id, reused = _provision_railway(project, region or "us-west", reuse)
        manifest = {"provider": "railway", "projectId": project_id, "reused": reused}
    elif provider == "self-hosted":
        url, host_id, reused = _provision_self_hosted(project)
        manifest = {"provider": "self-hosted", "hostId": host_id, "reused": reused}
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    set_secret(project, "DATABASE_URL", url)
    from apps.projects.scan_data_utils import update_project_scan_data

    update_project_scan_data(project, {"postgres": manifest})

    result = {
        "provider": provider,
        "stored": True,
        "reused": manifest.get("reused", False),
        "message": f"{'Reused' if manifest.get('reused') else 'Created'} {provider} database — DATABASE_URL stored in vault",
    }
    if apply_schema:
        schema = apply_postgres_schema(project)
        result["schema"] = schema
        if schema["ok"]:
            result["message"] += " — schema applied"
    return result
