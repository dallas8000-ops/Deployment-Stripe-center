"""Post-deploy Stripe webhook health — API metadata only."""

from __future__ import annotations

from typing import Any

import stripe

from apps.projects.models import Project
from apps.stripe_core.hub_keys import resolve_expected_webhook_url
from apps.vault.models import get_secret


def webhook_health(project: Project) -> dict[str, Any]:
    secret = get_secret(project, "STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("STRIPE_SECRET_KEY not in vault")

    stripe.api_key = secret
    expected = resolve_expected_webhook_url(project) or None

    endpoints = stripe.WebhookEndpoint.list(limit=10)
    endpoint_rows: list[dict[str, Any]] = []
    for ep in endpoints.data:
        row = {
            "id": ep.id,
            "url": ep.url,
            "status": ep.status,
            "enabledEvents": len(ep.enabled_events or []),
            "matchesExpected": ep.url == expected if expected else None,
        }
        endpoint_rows.append(row)

    recent_types: dict[str, int] = {}
    try:
        events = stripe.Event.list(limit=25)
        for ev in events.data:
            recent_types[ev.type] = recent_types.get(ev.type, 0) + 1
    except stripe.StripeError:
        events = None

    issues = []
    if expected and not any(r.get("matchesExpected") for r in endpoint_rows):
        issues.append(
            {
                "severity": "warning",
                "message": f"No webhook endpoint matches expected URL {expected}",
                "fix": "Run provision-stripe or update webhook in Stripe Dashboard",
            }
        )
    disabled = [r for r in endpoint_rows if r.get("status") != "enabled"]
    for row in disabled:
        issues.append(
            {
                "severity": "error",
                "message": f"Webhook {row['id']} is {row['status']}",
                "fix": "Enable endpoint in Stripe Dashboard",
            }
        )

    return {
        "expectedWebhookUrl": expected,
        "endpoints": endpoint_rows,
        "recentEventTypes": recent_types,
        "issues": issues,
        "healthy": len(issues) == 0,
    }
