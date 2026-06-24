"""Automated webhook testing and validation."""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import stripe

from apps.deploy.postgres import get_production_url
from apps.projects.models import Project
from apps.stripe_core.pipeline import _webhook_path
from apps.diagnostics.webhook_events import fetch_stripe_event
from apps.vault.models import get_secret


@dataclass
class WebhookTestResult:
    """Result of a webhook test."""
    test_type: str
    success: bool
    message: str
    details: dict[str, Any]
    timestamp: str
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "testType": self.test_type,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "durationMs": self.duration_ms,
        }


def _test_webhook_endpoint_reachable(project: Project) -> WebhookTestResult:
    """Test if webhook endpoint is reachable."""
    start = time.time()
    try:
        prod_url = get_production_url(project, "")
        if not prod_url:
            return WebhookTestResult(
                test_type="endpoint_reachable",
                success=False,
                message="Production URL not configured",
                details={},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )

        webhook_path = _webhook_path(project.framework or "unknown")
        webhook_url = f"{prod_url.rstrip('/')}{webhook_path}"

        # Try to fetch the endpoint (HEAD request would be better but we'll use a simple check)
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(webhook_url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as response:
                success = response.status < 400
                return WebhookTestResult(
                    test_type="endpoint_reachable",
                    success=success,
                    message=f"Webhook endpoint returned {response.status}",
                    details={"url": webhook_url, "statusCode": response.status},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    duration_ms=(time.time() - start) * 1000,
                )
        except urllib.error.HTTPError as e:
            return WebhookTestResult(
                test_type="endpoint_reachable",
                success=e.code < 500,  # 4xx might be expected for HEAD
                message=f"HTTP Error: {e.code}",
                details={"url": webhook_url, "statusCode": e.code},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )
        except urllib.error.URLError as e:
            return WebhookTestResult(
                test_type="endpoint_reachable",
                success=False,
                message=f"Connection failed: {str(e)}",
                details={"url": webhook_url, "error": str(e)},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )
    except Exception as exc:
        return WebhookTestResult(
            test_type="endpoint_reachable",
            success=False,
            message=str(exc),
            details={"error": str(exc)},
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.time() - start) * 1000,
        )


def _test_webhook_signature_verification(project: Project) -> WebhookTestResult:
    """Test webhook signature verification setup."""
    start = time.time()
    try:
        secret = get_secret(project, "STRIPE_WEBHOOK_SECRET")
        if not secret:
            return WebhookTestResult(
                test_type="signature_verification",
                success=False,
                message="STRIPE_WEBHOOK_SECRET not configured",
                details={},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )

        # Check if secret looks valid (starts with whsec_)
        if not secret.startswith("whsec_"):
            return WebhookTestResult(
                test_type="signature_verification",
                success=False,
                message="Invalid webhook secret format (should start with whsec_)",
                details={"secretPrefix": secret[:10] if len(secret) > 10 else secret},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )

        return WebhookTestResult(
            test_type="signature_verification",
            success=True,
            message="Webhook secret configured",
            details={"secretLength": len(secret)},
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.time() - start) * 1000,
        )
    except Exception as exc:
        return WebhookTestResult(
            test_type="signature_verification",
            success=False,
            message=str(exc),
            details={"error": str(exc)},
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.time() - start) * 1000,
        )


def _test_stripe_webhook_registration(project: Project) -> WebhookTestResult:
    """Test if webhook is registered in Stripe."""
    start = time.time()
    try:
        secret = get_secret(project, "STRIPE_SECRET_KEY")
        if not secret:
            return WebhookTestResult(
                test_type="stripe_registration",
                success=False,
                message="STRIPE_SECRET_KEY not configured",
                details={},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )

        stripe.api_key = secret
        prod_url = get_production_url(project, "")
        webhook_path = _webhook_path(project.framework or "unknown")
        expected_url = f"{prod_url.rstrip('/')}{webhook_path}" if prod_url else None

        endpoints = stripe.WebhookEndpoint.list(limit=20)
        matching = [ep for ep in endpoints.data if ep.url == expected_url] if expected_url else []

        if not matching:
            return WebhookTestResult(
                test_type="stripe_registration",
                success=False,
                message=f"No webhook registered for {expected_url}",
                details={"expectedUrl": expected_url, "registeredCount": len(endpoints.data)},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )

        endpoint = matching[0]
        return WebhookTestResult(
            test_type="stripe_registration",
            success=endpoint.status == "enabled",
            message=f"Webhook registered and {endpoint.status}",
            details={
                "endpointId": endpoint.id,
                "url": endpoint.url,
                "status": endpoint.status,
                "enabledEvents": len(endpoint.enabled_events or []),
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.time() - start) * 1000,
        )
    except Exception as exc:
        return WebhookTestResult(
            test_type="stripe_registration",
            success=False,
            message=str(exc),
            details={"error": str(exc)},
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.time() - start) * 1000,
        )


def _test_webhook_event_delivery(project: Project) -> WebhookTestResult:
    """Test webhook event delivery by checking recent events."""
    start = time.time()
    try:
        secret = get_secret(project, "STRIPE_SECRET_KEY")
        if not secret:
            return WebhookTestResult(
                test_type="event_delivery",
                success=False,
                message="STRIPE_SECRET_KEY not configured",
                details={},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )

        stripe.api_key = secret
        events = stripe.Event.list(limit=10)

        if not events.data:
            return WebhookTestResult(
                test_type="event_delivery",
                success=True,
                message="No recent events (normal for new accounts)",
                details={"eventCount": 0},
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_ms=(time.time() - start) * 1000,
            )

        # Check for recent successful events
        recent_events = [e for e in events.data if e.created > (time.time() - 86400)]  # Last 24h
        event_types = Counter([e.type for e in recent_events])

        return WebhookTestResult(
            test_type="event_delivery",
            success=True,
            message=f"Found {len(recent_events)} events in last 24h",
            details={
                "recentEventCount": len(recent_events),
                "eventTypes": dict(event_types),
                "latestEvent": events.data[0].type if events.data else None,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.time() - start) * 1000,
        )
    except Exception as exc:
        return WebhookTestResult(
            test_type="event_delivery",
            success=False,
            message=str(exc),
            details={"error": str(exc)},
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=(time.time() - start) * 1000,
        )


def run_webhook_test_suite(project: Project) -> dict[str, Any]:
    """Run complete webhook test suite."""
    tests = [
        _test_webhook_endpoint_reachable(project),
        _test_webhook_signature_verification(project),
        _test_stripe_webhook_registration(project),
        _test_webhook_event_delivery(project),
    ]

    total_duration = sum(t.duration_ms for t in tests)
    passed = sum(1 for t in tests if t.success)
    failed = len(tests) - passed

    return {
        "summary": {
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            "durationMs": total_duration,
            "overallSuccess": failed == 0,
        },
        "tests": [t.to_dict() for t in tests],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
