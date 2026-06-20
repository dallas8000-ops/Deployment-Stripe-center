"""Fetch and sanitize Stripe webhook events for AI analysis — never expose secrets."""

from __future__ import annotations

import re
from typing import Any

import stripe

from apps.projects.models import Project
from apps.vault.models import get_secret

_EVENT_ID_RE = re.compile(r"^evt_[a-zA-Z0-9]+$")

_SENSITIVE_KEYS = frozenset(
    {
        "client_secret",
        "secret",
        "password",
        "payment_method",
        "source",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "private_key",
        "card",
        "number",
        "cvc",
        "exp_month",
        "exp_year",
    }
)

_MAX_DEPTH = 6
_MAX_STRING = 200
_MAX_LIST = 20


def _truncate(value: str) -> str:
    if len(value) <= _MAX_STRING:
        return value
    return value[:_MAX_STRING] + "…"


def sanitize_stripe_value(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        return "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate(value)
    if isinstance(value, list):
        return [sanitize_stripe_value(v, depth=depth + 1) for v in value[:_MAX_LIST]]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in list(value.items())[:40]:
            key_lower = str(key).lower()
            if key_lower in _SENSITIVE_KEYS or key_lower.endswith("_secret"):
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = sanitize_stripe_value(item, depth=depth + 1)
        return cleaned
    return _truncate(str(value))


def fetch_stripe_event(project: Project, event_id: str) -> dict[str, Any]:
    event_id = (event_id or "").strip()
    if not _EVENT_ID_RE.match(event_id):
        raise ValueError("event_id must look like evt_…")

    secret = get_secret(project, "STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("STRIPE_SECRET_KEY not in vault")

    stripe.api_key = secret
    event = stripe.Event.retrieve(event_id)
    payload = event.to_dict() if hasattr(event, "to_dict") else dict(event)

    sanitized = sanitize_stripe_value(payload)
    if not isinstance(sanitized, dict):
        sanitized = {"event": sanitized}

    return {
        "id": sanitized.get("id"),
        "type": sanitized.get("type"),
        "livemode": sanitized.get("livemode"),
        "created": sanitized.get("created"),
        "api_version": sanitized.get("api_version"),
        "data": sanitized.get("data"),
        "request": sanitized.get("request"),
    }
