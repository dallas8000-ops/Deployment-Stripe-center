"""Push vault secrets directly to Render or Railway service environment variables."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from apps.projects.models import Project
from apps.vault.models import get_secret

STRIPE_ENV_KEYS = [
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
    "DATABASE_URL",
]

RENDER_API = "https://api.render.com/v1"
RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"


def _http_json(method: str, url: str, headers: dict, body: Any = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def push_to_render(api_key: str, service_id: str, env_vars: dict[str, str]) -> dict[str, Any]:
    payload = [{"key": k, "value": v} for k, v in sorted(env_vars.items())]
    _http_json(
        "PUT",
        f"{RENDER_API}/services/{service_id}/env-vars",
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        payload,
    )
    return {"pushed": sorted(env_vars.keys())}


def _railway_gql(token: str, query: str, variables: dict | None = None) -> dict:
    body = {"query": query, "variables": variables or {}}
    req = urllib.request.Request(
        RAILWAY_GQL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Railway API {exc.code}: {exc.read().decode()[:300]}") from exc
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"])[:300])
    return payload.get("data", {})


def _railway_environment_id(token: str, project_id: str) -> str:
    data = _railway_gql(
        token,
        "query($id: String!) { project(id: $id) { environments { edges { node { id } } } } }",
        {"id": project_id},
    )
    edges = ((data.get("project") or {}).get("environments") or {}).get("edges") or []
    env_id = ((edges[0] if edges else {}).get("node") or {}).get("id")
    if not env_id:
        raise RuntimeError("No environment found for Railway project")
    return env_id


def push_to_railway(
    token: str,
    project_id: str,
    service_id: str,
    env_vars: dict[str, str],
    environment_id: str | None = None,
) -> dict[str, Any]:
    if not environment_id:
        environment_id = _railway_environment_id(token, project_id)
    _railway_gql(
        token,
        "mutation($input: VariableCollectionUpsertInput!) { variableCollectionUpsert(input: $input) }",
        {
            "input": {
                "projectId": project_id,
                "serviceId": service_id,
                "environmentId": environment_id,
                "variables": env_vars,
            }
        },
    )
    return {"pushed": sorted(env_vars.keys()), "environmentId": environment_id}


def push_vault_env_to_platform(
    project: Project,
    platform: str,
    service_id: str,
    *,
    project_id: str | None = None,
    environment_id: str | None = None,
    keys: list[str] | None = None,
) -> dict[str, Any]:
    """Read vault secrets and push them to the given platform service."""
    target_keys = keys or STRIPE_ENV_KEYS
    env_vars = {k: v for k in target_keys if (v := get_secret(project, k))}
    if not env_vars:
        return {"pushed": [], "message": "No matching secrets found in vault"}

    if platform == "render":
        api_key = get_secret(project, "RENDER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "RENDER_API_KEY not in vault — add it at https://dashboard.render.com/u/settings#api-keys"
            )
        result = push_to_render(api_key, service_id, env_vars)

    elif platform == "railway":
        token = get_secret(project, "RAILWAY_API_TOKEN")
        if not token:
            raise RuntimeError(
                "RAILWAY_API_TOKEN not in vault — create at https://railway.com/account/tokens"
            )
        if not project_id:
            raise RuntimeError("project_id is required for Railway env push")
        result = push_to_railway(token, project_id, service_id, env_vars, environment_id)

    else:
        raise ValueError(f"Unsupported platform '{platform}' — supported: render, railway")

    result["message"] = (
        f"Pushed {len(env_vars)} var(s) to {platform}: {', '.join(sorted(env_vars.keys()))}"
    )
    return result
