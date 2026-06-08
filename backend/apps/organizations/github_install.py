"""GitHub App installation flow for organizations."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

from django.conf import settings

from apps.organizations.models import Organization


def github_app_configured() -> bool:
    return bool(getattr(settings, "GITHUB_APP_SLUG", "").strip())


def github_app_slug() -> str:
    slug = getattr(settings, "GITHUB_APP_SLUG", "").strip()
    if not slug:
        raise RuntimeError("GITHUB_APP_SLUG is not configured")
    return slug


def setup_callback_url() -> str:
    explicit = getattr(settings, "GITHUB_APP_SETUP_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    base = getattr(settings, "SAAS_BILLING_RETURN_URL", "http://localhost:5173").rstrip("/")
    return f"{base}/agency/github/callback"


def build_install_state(org: Organization) -> str:
    token = secrets.token_urlsafe(12)
    return f"{org.slug}:{token}"


def build_install_url(org: Organization) -> dict:
    slug = github_app_slug()
    state = build_install_state(org)
    params = urlencode({"state": state})
    return {
        "url": f"https://github.com/apps/{slug}/installations/new?{params}",
        "state": state,
        "callbackUrl": setup_callback_url(),
    }


def parse_install_state(state: str) -> str | None:
    if not state or ":" not in state:
        if state and "/" not in state:
            return state.strip()
        return None
    org_slug, _token = state.split(":", 1)
    return org_slug.strip() or None


def verify_installation(installation_id: int | str) -> dict:
    from apps.projects.github_app import github_app_configured as has_key, _github_app_api

    if not has_key():
        return {"installationId": installation_id, "verified": False}

    data = _github_app_api("GET", f"/app/installations/{installation_id}")
    account = data.get("account") or {}
    return {
        "installationId": data.get("id"),
        "accountLogin": account.get("login"),
        "accountType": account.get("type"),
        "repositorySelection": data.get("repository_selection"),
        "verified": True,
    }


def apply_installation(org: Organization, installation_id: int, account_login: str = "") -> Organization:
    org.github_installation_id = installation_id
    if account_login:
        org.github_account = account_login
    org.save(update_fields=["github_installation_id", "github_account", "updated_at"])
    return org
