"""Push vault secrets and/or inline variables to Railway service environment."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from apps.projects.models import Project
from apps.vault.models import get_secret, vault_health

STRIPE_ENV_KEYS = [
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
    "DATABASE_URL",
]

# Non-secret defaults — override DATABASE_URL / secrets via vault or request `variables`.
KISTIE_STORE_PRESET: dict[str, str] = {
    "DJANGO_DEBUG": "False",
    "DJANGO_ENABLE_ADMIN": "False",
    "DATABASE_URL": "${{Postgres.DATABASE_URL}}",
    "ALLOWED_HOSTS": ".railway.app kistie-store-production.up.railway.app",
    "CSRF_TRUSTED_ORIGINS": "https://kistie-store-production.up.railway.app",
    "SITE_URL": "https://kistie-store-production.up.railway.app",
    "DJANGO_EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.gmail.com",
    "EMAIL_PORT": "587",
    "EMAIL_USE_TLS": "True",
    "CONTACT_RECIPIENT_EMAIL": "dallas8000@gmail.com",
    "DJANGO_DEFAULT_FROM_EMAIL": "dallas8000@gmail.com",
    "ORDER_ALERT_EMAIL": "dallas8000@gmail.com",
    "WHATSAPP_STORE_NUMBER": "256704757198",
    "INSTAGRAM_PROFILE_URL": "https://www.instagram.com/kistie_storeug/",
}

KISTIE_STORE_VAULT_KEYS = [
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
]

# SilverFox — men's Django SSR storefront (separate Postgres from Kistie Store).
SILVERFOX_PRESET: dict[str, str] = {
    "DEBUG": "False",
    "DJANGO_ENABLE_ADMIN": "True",
    "DJANGO_SSL_REDIRECT": "True",
    "DATABASE_URL": "${{Postgres.DATABASE_URL}}",
    "ALLOWED_HOSTS": ".railway.app .up.railway.app silverfox-production.up.railway.app",
    "CSRF_TRUSTED_ORIGINS": "https://silverfox-production.up.railway.app",
}

SILVERFOX_VAULT_KEYS = [
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
]

ENV_PRESETS: dict[str, dict[str, str]] = {
    "kistie-store": KISTIE_STORE_PRESET,
    "silverfox": SILVERFOX_PRESET,
}

PRESET_VAULT_KEYS: dict[str, list[str]] = {
    "kistie-store": KISTIE_STORE_VAULT_KEYS,
    "silverfox": SILVERFOX_VAULT_KEYS,
}

RAILWAY_GQL = "https://backboard.railway.app/graphql/v2"


def merge_env_vars(
    *,
    preset: dict[str, str] | None = None,
    vault: dict[str, str] | None = None,
    inline: dict[str, str] | None = None,
) -> dict[str, str]:
    """Merge preset → vault → inline (later sources override earlier)."""
    merged: dict[str, str] = {}
    if preset:
        merged.update({k: v for k, v in preset.items() if v is not None and str(v).strip()})
    if vault:
        merged.update({k: v for k, v in vault.items() if v})
    if inline:
        merged.update({k: str(v).strip() for k, v in inline.items() if v is not None and str(v).strip()})
    return merged


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


def _vault_subset(project: Project, keys: list[str]) -> dict[str, str]:
    return {k: v for k in keys if (v := get_secret(project, k))}


def build_env_var_payload(
    project: Project,
    *,
    keys: list[str] | None = None,
    variables: dict[str, str] | None = None,
    preset: str | None = None,
) -> dict[str, str]:
    preset_vars = ENV_PRESETS.get(preset or "", {})
    vault_keys = keys
    if preset and not vault_keys:
        vault_keys = PRESET_VAULT_KEYS.get(preset, [])
    if not vault_keys and not preset_vars and not variables:
        vault_keys = STRIPE_ENV_KEYS
    vault_vars = _vault_subset(project, vault_keys or [])
    return merge_env_vars(preset=preset_vars or None, vault=vault_vars or None, inline=variables)


def push_vault_env_to_platform(
    project: Project,
    platform: str,
    service_id: str,
    *,
    project_id: str | None = None,
    environment_id: str | None = None,
    keys: list[str] | None = None,
    variables: dict[str, str] | None = None,
    preset: str | None = None,
) -> dict[str, Any]:
    """Push vault secrets, optional preset defaults, and inline variables to Railway."""
    if platform != "railway":
        raise ValueError(f"Unsupported platform '{platform}' — supported: railway")

    token = get_secret(project, "RAILWAY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "RAILWAY_API_TOKEN not in vault — create at https://railway.com/account/tokens"
        )
    if not project_id:
        raise RuntimeError("project_id is required for Railway env push")

    if preset and preset not in ENV_PRESETS:
        raise ValueError(f"Unknown preset '{preset}' — available: {', '.join(sorted(ENV_PRESETS))}")

    inline = None
    if variables:
        if not isinstance(variables, dict):
            raise ValueError("variables must be an object of key/value strings")
        inline = {str(k): str(v) for k, v in variables.items()}

    env_vars = build_env_var_payload(project, keys=keys, variables=inline, preset=preset)
    if not env_vars:
        health = vault_health(project)
        if health["unreadableCount"]:
            raise RuntimeError(
                f"Cannot push env vars: {health['unreadableCount']} vault secret(s) cannot be "
                "decrypted. Restore ~/.stripe-installer/projects/ backup or re-enter keys in the vault."
            )
        return {"pushed": [], "message": "No variables to push (empty preset, vault, and inline)"}

    result = push_to_railway(token, project_id, service_id, env_vars, environment_id)
    result["preset"] = preset
    result["message"] = (
        f"Pushed {len(env_vars)} var(s) to {platform}: {', '.join(sorted(env_vars.keys()))}"
    )
    return result
