"""Enterprise OIDC SSO (Okta, Azure AD, Google Workspace, etc.)."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache

STATE_SALT = "accounts.sso.state"
STATE_MAX_AGE_SECONDS = 600


def sso_enabled() -> bool:
    return bool(
        getattr(settings, "OIDC_SSO_ENABLED", False)
        and getattr(settings, "OIDC_ISSUER_URL", "")
        and getattr(settings, "OIDC_CLIENT_ID", "")
        and getattr(settings, "OIDC_CLIENT_SECRET", "")
    )


def _issuer() -> str:
    return str(settings.OIDC_ISSUER_URL).rstrip("/")


def _redirect_uri() -> str:
    explicit = getattr(settings, "OIDC_REDIRECT_URI", "")
    if explicit:
        return explicit.rstrip("/") + "/"
    base = getattr(settings, "APP_PUBLIC_URL", "http://localhost:5173").rstrip("/")
    return f"{base}/api/v1/auth/sso/callback/"


def _frontend_callback_url() -> str:
    base = getattr(settings, "APP_PUBLIC_URL", "http://localhost:5173").rstrip("/")
    return f"{base}/auth/sso/callback"


def fetch_oidc_metadata() -> dict[str, Any]:
    url = f"{_issuer()}/.well-known/openid-configuration"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    return res.json()


def issue_sso_state() -> str:
    state = secrets.token_urlsafe(24)
    signed = signing.TimestampSigner(salt=STATE_SALT).sign(state)
    cache.set(f"sso:state:{state}", True, timeout=STATE_MAX_AGE_SECONDS)
    return signed


def verify_sso_state(signed_state: str) -> str:
    state = signing.TimestampSigner(salt=STATE_SALT).unsign(
        signed_state, max_age=STATE_MAX_AGE_SECONDS
    )
    if not cache.get(f"sso:state:{state}"):
        raise ValueError("SSO state expired or unknown")
    cache.delete(f"sso:state:{state}")
    return state


def build_authorize_url() -> str:
    meta = fetch_oidc_metadata()
    state = issue_sso_state()
    params = {
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "scope": getattr(settings, "OIDC_SCOPES", "openid email profile"),
        "state": state,
    }
    return f"{meta['authorization_endpoint']}?{urlencode(params)}"


def exchange_code_for_userinfo(code: str) -> dict[str, Any]:
    meta = fetch_oidc_metadata()
    token_res = requests.post(
        meta["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
            "client_id": settings.OIDC_CLIENT_ID,
            "client_secret": settings.OIDC_CLIENT_SECRET,
        },
        timeout=15,
    )
    token_res.raise_for_status()
    tokens = token_res.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise ValueError("OIDC token response missing access_token")

    userinfo_res = requests.get(
        meta["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    userinfo_res.raise_for_status()
    return userinfo_res.json()


def email_allowed_for_sso(email: str) -> bool:
    allowed = getattr(settings, "OIDC_ALLOWED_EMAIL_DOMAINS", [])
    if not allowed:
        return True
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in {d.lower() for d in allowed}


def provision_user_from_oidc(userinfo: dict[str, Any]):
    from django.contrib.auth import get_user_model

    email = (
        str(userinfo.get("email") or userinfo.get("preferred_username") or "")
        .strip()
        .lower()
    )
    if not email or "@" not in email:
        raise ValueError("OIDC userinfo did not include an email address")
    if not email_allowed_for_sso(email):
        raise ValueError(f"Email domain not allowed for SSO: {email}")

    User = get_user_model()
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "display_name": str(userinfo.get("name") or userinfo.get("given_name") or "")[:150],
            "is_active": True,
        },
    )
    if not created and not user.is_active:
        raise ValueError("Account is disabled")
    return user


def frontend_redirect_with_tokens(access: str, refresh: str) -> str:
    fragment = urlencode({"access": access, "refresh": refresh})
    return f"{_frontend_callback_url()}#{fragment}"
