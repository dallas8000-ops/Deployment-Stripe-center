"""Stripe Setup Advisor — classify webhook failures and step-by-step playbooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from apps.deploy.postgres import get_production_url
from apps.projects.models import Project
from apps.stripe_installer.pipeline import _webhook_path
from apps.stripe_installer.portfolio_audit import _probe_url
from apps.diagnostics.webhook_health import webhook_health
from apps.stripe_installer.webhook_tester import run_webhook_test_suite
from apps.stripe_installer.verify import verify_stripe_keys
from apps.vault.models import get_secret, list_secret_keys

STRIPE_TEST_KEYS = "https://dashboard.stripe.com/test/apikeys"
STRIPE_LIVE_KEYS = "https://dashboard.stripe.com/apikeys"
STRIPE_TEST_WEBHOOKS = "https://dashboard.stripe.com/test/webhooks"
STRIPE_LIVE_WEBHOOKS = "https://dashboard.stripe.com/webhooks"


class RootCause(str, Enum):
    KEYS_MISSING = "KEYS_MISSING"
    KEYS_INVALID = "KEYS_INVALID"
    NO_PRODUCTION_URL = "NO_PRODUCTION_URL"
    HOSTING_DOWN = "HOSTING_DOWN"
    WEBHOOK_NOT_REGISTERED = "WEBHOOK_NOT_REGISTERED"
    ENDPOINT_DISABLED = "ENDPOINT_DISABLED"
    WEBHOOK_SECRET_MISSING = "WEBHOOK_SECRET_MISSING"
    WEBHOOK_SECRET_INVALID = "WEBHOOK_SECRET_INVALID"
    DELIVERY_LIKELY_FAILING = "DELIVERY_LIKELY_FAILING"
    HEALTHY = "HEALTHY"


@dataclass
class PlaybookStep:
    order: int
    title: str
    detail: str
    where: str  # stripe_dashboard | hosting | vault | installer
    url: str | None = None
    confirm: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "title": self.title,
            "detail": self.detail,
            "where": self.where,
            "url": self.url,
            "confirm": self.confirm,
        }


@dataclass
class AdvisorFinding:
    root_cause: RootCause
    severity: str
    title: str
    summary: str
    playbook: list[PlaybookStep] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rootCause": self.root_cause.value,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "playbook": [s.to_dict() for s in self.playbook],
            "metrics": self.metrics,
        }


def _dashboard_links(mode: str) -> dict[str, str]:
    if mode == "live":
        return {"keys": STRIPE_LIVE_KEYS, "webhooks": STRIPE_LIVE_WEBHOOKS}
    return {"keys": STRIPE_TEST_KEYS, "webhooks": STRIPE_TEST_WEBHOOKS}


def _playbook_keys_missing(links: dict[str, str]) -> list[PlaybookStep]:
    return [
        PlaybookStep(
            1,
            "Open Stripe API keys",
            "Copy your secret and publishable keys (test or live — use one mode consistently).",
            "stripe_dashboard",
            links["keys"],
            "Keys start with sk_ and pk_ for the same mode (test or live).",
        ),
        PlaybookStep(
            2,
            "Add keys to Stripe Installer vault",
            "Projects → Vault → STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY. Never commit keys to git.",
            "vault",
            confirm="Vault shows both keys as stored.",
        ),
        PlaybookStep(
            3,
            "Re-run advisor",
            "Confirm keys verify and webhook checks can run.",
            "installer",
            confirm="Advisor shows keys valid.",
        ),
    ]


def _playbook_hosting_down(
    prod_url: str,
    health_url: str,
    webhook_url: str,
    links: dict[str, str],
) -> list[PlaybookStep]:
    return [
        PlaybookStep(
            1,
            "Confirm the app is down (not a Stripe bug)",
            "100% webhook errors usually mean Stripe reaches your URL but gets 502/timeout. Fix hosting before Stripe settings.",
            "installer",
            confirm=f"Health URL responds: {health_url}",
        ),
        PlaybookStep(
            2,
            "Fix production deploy",
            "On Railway/Render: deploy latest commit (not Redeploy old image), Dockerfile/start command, DJANGO_SECRET_KEY and DATABASE_URL on the web service.",
            "hosting",
            url=prod_url,
            confirm="Browser or curl shows 200 on /health/ — not 502.",
        ),
        PlaybookStep(
            3,
            "Check Stripe only after app is live",
            "Open Webhooks → your endpoint → Event deliveries. Errors should drop once the app returns 2xx.",
            "stripe_dashboard",
            links["webhooks"],
            confirm="Recent deliveries show 200, not 100% failed.",
        ),
    ]


def _playbook_secret_missing(links: dict[str, str], endpoint_url: str) -> list[PlaybookStep]:
    return [
        PlaybookStep(
            1,
            "Open the webhook in Stripe",
            "Developers → Webhooks → select the endpoint matching your production URL.",
            "stripe_dashboard",
            links["webhooks"],
        ),
        PlaybookStep(
            2,
            "Reveal signing secret",
            "Copy whsec_… (or re-register endpoint to get a new secret).",
            "stripe_dashboard",
            links["webhooks"],
            confirm="Secret starts with whsec_.",
        ),
        PlaybookStep(
            3,
            "Set STRIPE_WEBHOOK_SECRET",
            "Vault in Stripe Installer, then the same value on your host (Railway/Render env).",
            "vault",
            confirm="Host env matches Dashboard signing secret.",
        ),
        PlaybookStep(
            4,
            "Verify deliveries",
            f"Endpoint URL should be: {endpoint_url}",
            "stripe_dashboard",
            links["webhooks"],
            confirm="Error rate no longer 100%.",
        ),
    ]


def _playbook_not_registered(webhook_url: str, links: dict[str, str]) -> list[PlaybookStep]:
    return [
        PlaybookStep(
            1,
            "Register webhook endpoint",
            f"Add endpoint URL: {webhook_url}",
            "stripe_dashboard",
            links["webhooks"],
        ),
        PlaybookStep(
            2,
            "Or auto-register from Installer",
            "Run full setup pipeline (provision) once production URL is set and app is live.",
            "installer",
            confirm="Webhook appears in Stripe Dashboard list.",
        ),
        PlaybookStep(
            3,
            "Store signing secret",
            "Copy whsec_ to vault and host environment.",
            "vault",
        ),
    ]


def run_stripe_advisor(project: Project, project_root: Path | None = None) -> dict[str, Any]:
    """Build advisor report: classify root cause + ordered playbook."""
    secret = get_secret(project, "STRIPE_SECRET_KEY")
    publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
    vault_keys = list_secret_keys(project)
    verification = verify_stripe_keys(secret, publishable)
    mode = verification.secret_key.mode if verification.secret_key.valid else "test"
    links = _dashboard_links(mode if mode in ("test", "live") else "test")

    prod_url = ""
    if project_root and project_root.is_dir():
        prod_url = get_production_url(project, "")
    if not prod_url:
        prod_url = str((project.scan_data or {}).get("productionUrl") or "").rstrip("/")

    webhook_path = _webhook_path(project.framework or "unknown", project.scan_data)
    webhook_url = f"{prod_url.rstrip('/')}{webhook_path}" if prod_url else ""
    health_url = f"{prod_url.rstrip('/')}/health/?format=json" if prod_url else ""

    findings: list[AdvisorFinding] = []
    checks: dict[str, Any] = {
        "productionUrl": prod_url,
        "expectedWebhookUrl": webhook_url,
        "healthUrl": health_url,
        "vaultKeys": vault_keys,
        "keyVerification": verification.to_public_dict(),
    }

    if "STRIPE_SECRET_KEY" not in vault_keys:
        findings.append(
            AdvisorFinding(
                RootCause.KEYS_MISSING,
                "error",
                "Stripe account not linked",
                "Add API keys to the vault before webhook checks can run.",
                _playbook_keys_missing(links),
            )
        )
    elif not verification.secret_key.valid:
        findings.append(
            AdvisorFinding(
                RootCause.KEYS_INVALID,
                "error",
                "Invalid Stripe secret key",
                verification.secret_key.message,
                _playbook_keys_missing(links),
            )
        )

    if not prod_url:
        findings.append(
            AdvisorFinding(
                RootCause.NO_PRODUCTION_URL,
                "error",
                "Production URL not set",
                "Set productionUrl in deploy.config.json or scan_data so the advisor knows where webhooks should point.",
                [
                    PlaybookStep(
                        1,
                        "Set production URL",
                        "Deploy config → production URL (e.g. https://your-app.up.railway.app).",
                        "installer",
                        confirm="productionUrl saved on project.",
                    ),
                    PlaybookStep(
                        2,
                        "Re-run advisor",
                        "Webhook URL will be derived from framework + path.",
                        "installer",
                    ),
                ],
            )
        )

    probe = _probe_url(webhook_url) if webhook_url else None
    health_probe = _probe_url(health_url) if health_url else None
    if probe:
        checks["webhookProbe"] = probe.to_dict()
    if health_probe:
        checks["healthProbe"] = health_probe.to_dict()

    hosting_down = bool(
        webhook_url
        and probe
        and not probe.reachable
        and (probe.status_code is None or (probe.status_code or 0) >= 500)
    )
    if hosting_down:
        findings.append(
            AdvisorFinding(
                RootCause.HOSTING_DOWN,
                "error",
                "Production app not reachable",
                probe.message if probe else "Webhook URL failed HTTP probe.",
                _playbook_hosting_down(prod_url, health_url, webhook_url, links),
                metrics={"statusCode": probe.status_code if probe else None},
            )
        )

    wh_health: dict[str, Any] | None = None
    if verification.secret_key.valid and secret:
        try:
            wh_health = webhook_health(project)
            checks["webhookHealth"] = wh_health
        except Exception as exc:
            checks["webhookHealthError"] = str(exc)

    if "STRIPE_WEBHOOK_SECRET" not in vault_keys and verification.secret_key.valid:
        findings.append(
            AdvisorFinding(
                RootCause.WEBHOOK_SECRET_MISSING,
                "warning",
                "Webhook signing secret not in vault",
                "Stripe may deliver events but your app cannot verify signatures without whsec_.",
                _playbook_secret_missing(links, webhook_url),
            )
        )
    else:
        whsec = get_secret(project, "STRIPE_WEBHOOK_SECRET") or ""
        if whsec and not whsec.startswith("whsec_"):
            findings.append(
                AdvisorFinding(
                    RootCause.WEBHOOK_SECRET_INVALID,
                    "error",
                    "Invalid webhook secret format",
                    "STRIPE_WEBHOOK_SECRET should start with whsec_.",
                    _playbook_secret_missing(links, webhook_url),
                )
            )

    if wh_health and prod_url and not hosting_down:
        if not wh_health.get("healthy"):
            for issue in wh_health.get("issues") or []:
                msg = issue.get("message", "")
                if "No webhook endpoint matches" in msg:
                    findings.append(
                        AdvisorFinding(
                            RootCause.WEBHOOK_NOT_REGISTERED,
                            "error",
                            "Webhook not registered in Stripe",
                            msg,
                            _playbook_not_registered(webhook_url, links),
                        )
                    )
        endpoints = wh_health.get("endpoints") or []
        for ep in endpoints:
            if ep.get("url") == webhook_url.rstrip("/") or ep.get("matchesExpected"):
                if ep.get("status") != "enabled":
                    findings.append(
                        AdvisorFinding(
                            RootCause.ENDPOINT_DISABLED,
                            "error",
                            "Webhook endpoint disabled in Stripe",
                            f"Enable endpoint {ep.get('id')} in Dashboard.",
                            [
                                PlaybookStep(
                                    1,
                                    "Enable webhook",
                                    "Developers → Webhooks → enable this endpoint.",
                                    "stripe_dashboard",
                                    links["webhooks"],
                                )
                            ],
                        )
                    )

    if (
        verification.secret_key.valid
        and prod_url
        and not hosting_down
        and wh_health
        and wh_health.get("healthy")
        and "STRIPE_WEBHOOK_SECRET" in vault_keys
    ):
        suite = run_webhook_test_suite(project)
        checks["webhookTestSuite"] = suite
        if not suite.get("summary", {}).get("overallSuccess"):
            findings.append(
                AdvisorFinding(
                    RootCause.DELIVERY_LIKELY_FAILING,
                    "warning",
                    "Webhook setup incomplete",
                    "Registration looks OK but tests failed — check Dashboard event deliveries for 100% errors.",
                    _playbook_secret_missing(links, webhook_url),
                    metrics={"failedTests": suite.get("summary", {}).get("failed")},
                )
            )

    if not findings:
        findings.append(
            AdvisorFinding(
                RootCause.HEALTHY,
                "info",
                "Webhooks look healthy",
                "Keys valid, endpoint registered, URL reachable. Re-run after deploy changes.",
                [
                    PlaybookStep(
                        1,
                        "Monitor Stripe Dashboard",
                        "Developers → Webhooks → confirm error rate stays at 0%.",
                        "stripe_dashboard",
                        links["webhooks"],
                    )
                ],
            )
        )

    # Primary = highest severity finding for summary
    severity_order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: severity_order.get(f.severity, 9))
    primary = findings[0]

    return {
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "projectName": project.name,
        "projectSlug": project.slug,
        "primaryRootCause": primary.root_cause.value,
        "webhookErrorRisk": primary.root_cause
        in (
            RootCause.HOSTING_DOWN,
            RootCause.WEBHOOK_SECRET_MISSING,
            RootCause.WEBHOOK_SECRET_INVALID,
            RootCause.WEBHOOK_NOT_REGISTERED,
            RootCause.ENDPOINT_DISABLED,
            RootCause.DELIVERY_LIKELY_FAILING,
            RootCause.KEYS_MISSING,
            RootCause.KEYS_INVALID,
        ),
        "summary": primary.summary,
        "dashboardLinks": links,
        "findings": [f.to_dict() for f in findings],
        "checks": checks,
    }
