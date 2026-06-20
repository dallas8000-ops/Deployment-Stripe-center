"""Account-wide Stripe webhook audit — local report only, no secrets in output."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import stripe

from apps.projects.models import Project
from apps.stripe_installer.portfolio_paths import portfolio_registry_path, portfolio_reports_dir
from apps.stripe_installer.portfolio_registry import PortfolioApp, find_app_by_webhook_url, load_registry
from apps.stripe_installer.provision import ProvisionConfig, provision_catalog
from apps.stripe_installer.verify import verify_stripe_keys
from apps.vault.models import get_secret

STRIPE_TEST_KEYS_URL = "https://dashboard.stripe.com/test/apikeys"
STRIPE_LIVE_KEYS_URL = "https://dashboard.stripe.com/apikeys"
STRIPE_WEBHOOKS_URL = "https://dashboard.stripe.com/webhooks"


@dataclass
class EndpointProbe:
    url: str
    reachable: bool
    status_code: int | None
    message: str
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "reachable": self.reachable,
            "statusCode": self.status_code,
            "message": self.message,
            "latencyMs": round(self.latency_ms, 1),
        }


@dataclass
class WebhookAuditRow:
    endpoint_id: str
    url: str
    status: str
    enabled_events: int
    matched_app: str | None
    probe: EndpointProbe | None
    issues: list[str] = field(default_factory=list)
    dashboard_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpointId": self.endpoint_id,
            "url": self.url,
            "status": self.status,
            "enabledEvents": self.enabled_events,
            "matchedApp": self.matched_app,
            "probe": self.probe.to_dict() if self.probe else None,
            "issues": self.issues,
            "dashboardUrl": self.dashboard_url,
        }


def _probe_url(url: str, *, timeout: float = 12.0) -> EndpointProbe:
    start = time.time()
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                code = response.status
                elapsed = (time.time() - start) * 1000
                # Webhooks expect POST; 405/401/400 often means the app is up.
                ok = code < 500
                return EndpointProbe(
                    url=url,
                    reachable=ok,
                    status_code=code,
                    message=f"{method} {code}",
                    latency_ms=elapsed,
                )
        except urllib.error.HTTPError as exc:
            elapsed = (time.time() - start) * 1000
            if exc.code < 500:
                return EndpointProbe(
                    url=url,
                    reachable=True,
                    status_code=exc.code,
                    message=f"{method} {exc.code} (app responding)",
                    latency_ms=elapsed,
                )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            continue
    elapsed = (time.time() - start) * 1000
    return EndpointProbe(
        url=url,
        reachable=False,
        status_code=None,
        message="Connection failed or timeout (app likely down — e.g. 502 on Railway)",
        latency_ms=elapsed,
    )


def _probe_health(app: PortfolioApp) -> EndpointProbe | None:
    if not app.health_url:
        return None
    health = app.health_url
    if "format=json" not in health:
        health = f"{health}{'&' if '?' in health else '?'}format=json"
    return _probe_url(health)


def _account_summary(secret_key: str) -> dict[str, Any]:
    stripe.api_key = secret_key
    account = stripe.Account.retrieve()
    mode = "live" if secret_key.startswith("sk_live_") else "test"
    return {
        "accountId": account.id,
        "mode": mode,
        "country": getattr(account, "country", None),
        "dashboardWebhooks": STRIPE_WEBHOOKS_URL if mode == "live" else "https://dashboard.stripe.com/test/webhooks",
        "dashboardKeys": STRIPE_LIVE_KEYS_URL if mode == "live" else STRIPE_TEST_KEYS_URL,
    }


def _recent_delivery_warnings(limit: int = 40) -> list[str]:
    warnings: list[str] = []
    try:
        events = stripe.Event.list(limit=limit)
        pending = [ev for ev in events.data if getattr(ev, "pending_webhooks", 0)]
        if pending:
            warnings.append(
                f"{len(pending)} recent event(s) still have pending webhook deliveries — check Dashboard → Webhooks → event log."
            )
    except stripe.StripeError as exc:
        warnings.append(f"Could not list recent events: {exc}")
    return warnings


def run_portfolio_audit(
    *,
    secret_key: str,
    publishable_key: str | None = None,
    registry_apps: list[PortfolioApp] | None = None,
) -> dict[str, Any]:
    registry = registry_apps if registry_apps is not None else load_registry()
    verification = verify_stripe_keys(secret_key, publishable_key)
    if not verification.secret_key.valid:
        raise ValueError(verification.secret_key.message)

    stripe.api_key = secret_key
    account = _account_summary(secret_key)
    delivery_warnings = _recent_delivery_warnings()

    endpoints = stripe.WebhookEndpoint.list(limit=100)
    rows: list[WebhookAuditRow] = []
    unmatched_registry = list(registry)

    for ep in endpoints.data:
        url = ep.url or ""
        matched = find_app_by_webhook_url(url, registry)
        if matched and matched in unmatched_registry:
            unmatched_registry.remove(matched)

        issues: list[str] = []
        if ep.status != "enabled":
            issues.append(f"Endpoint status is {ep.status}")
        probe = _probe_url(url)
        if not probe.reachable:
            issues.append(probe.message)

        if matched:
            health_probe = _probe_health(matched)
            if health_probe and not health_probe.reachable:
                issues.append(f"Health check failed: {matched.health_url} — {health_probe.message}")
            if matched.webhook_url.rstrip("/") != url.rstrip("/"):
                issues.append(
                    f"Registry expects {matched.webhook_url} but Stripe has {url}"
                )
        else:
            issues.append("Not in portfolio-registry.json allowedApps list")

        mode = account["mode"]
        dash_base = "https://dashboard.stripe.com/test/webhooks" if mode == "test" else STRIPE_WEBHOOKS_URL
        rows.append(
            WebhookAuditRow(
                endpoint_id=ep.id,
                url=url,
                status=ep.status or "unknown",
                enabled_events=len(ep.enabled_events or []),
                matched_app=matched.id if matched else None,
                probe=probe,
                issues=issues,
                dashboard_url=f"{dash_base}/{ep.id}",
            )
        )

    registry_gaps: list[dict[str, str]] = []
    for app in unmatched_registry:
        if app.stripe_exempt:
            continue
        if not app.requires_stripe_webhook:
            continue
        if not app.production_url:
            registry_gaps.append({"app": app.id, "issue": "productionUrl missing in registry"})
            continue
        registry_gaps.append(
            {
                "app": app.id,
                "issue": "No Stripe webhook endpoint registered for this app",
                "expectedUrl": app.webhook_url,
            }
        )

    failing = [r for r in rows if r.issues]
    return {
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "verification": verification.to_public_dict(),
        "deliveryWarnings": delivery_warnings,
        "registryPath": str(portfolio_registry_path()),
        "endpoints": [r.to_dict() for r in rows],
        "registryGaps": registry_gaps,
        "summary": {
            "endpointCount": len(rows),
            "failingCount": len(failing),
            "healthyCount": len(rows) - len(failing),
            "registryAppCount": len(registry),
        },
        "keyAutomationNote": (
            "Stripe does not allow creating standard sk_/pk_ secret keys via API. "
            "Create or rotate keys in the Dashboard links below, then import into the vault."
        ),
    }


def _markdown_report(data: dict[str, Any]) -> str:
    lines = [
        "# Stripe portfolio audit (local — do not commit)",
        "",
        f"Generated: {data['scannedAt']}",
        f"Registry: `{data['registryPath']}`",
        "",
        "## Account",
        "",
        f"- Account ID: `{data['account']['accountId']}`",
        f"- Mode: **{data['account']['mode']}**",
        f"- [API keys (Dashboard)]({data['account']['dashboardKeys']})",
        f"- [Webhooks (Dashboard)]({data['account']['dashboardWebhooks']})",
        "",
        "> " + data["keyAutomationNote"],
        "",
        "## Summary",
        "",
        f"- Webhook endpoints in Stripe: **{data['summary']['endpointCount']}**",
        f"- Failing or mismatched: **{data['summary']['failingCount']}**",
        f"- Registry apps configured: **{data['summary']['registryAppCount']}**",
        "",
    ]
    for warning in data.get("deliveryWarnings") or []:
        lines.append(f"- ⚠ {warning}")
    lines.append("")

    lines.extend(["## Webhook endpoints", ""])
    for ep in data["endpoints"]:
        status = "OK" if not ep["issues"] else "FAIL"
        lines.append(f"### [{status}] `{ep['url']}`")
        lines.append("")
        lines.append(f"- Stripe ID: `{ep['endpointId']}`")
        lines.append(f"- [Open in Stripe Dashboard]({ep['dashboardUrl']})")
        if ep.get("matchedApp"):
            lines.append(f"- Portfolio app: **{ep['matchedApp']}**")
        if ep.get("probe"):
            p = ep["probe"]
            lines.append(f"- HTTP probe: {p['message']} ({p['latencyMs']} ms)")
        for issue in ep.get("issues") or []:
            lines.append(f"- Issue: {issue}")
        lines.append("")

    if data.get("registryGaps"):
        lines.extend(["## Registry apps without matching Stripe endpoint", ""])
        for gap in data["registryGaps"]:
            lines.append(f"- **{gap['app']}**: {gap['issue']}")
            if gap.get("expectedUrl"):
                lines.append(f"  - Expected: `{gap['expectedUrl']}`")
        lines.append("")

    lines.extend(
        [
            "## Security",
            "",
            "This file is stored under your user profile only (`~/.stripe-installer/reports/`).",
            "It contains **no** API keys or webhook secrets. Do not copy into git repos.",
            "",
            "## Fix workflow",
            "",
            "1. If HTTP probe fails → fix hosting (app must answer on production URL).",
            "2. If endpoint missing → run `python manage.py stripe_installer portfolio-audit --fix --project <slug>`.",
            "3. Import `STRIPE_WEBHOOK_SECRET` into the host env (Railway/Render) after re-provision.",
            "4. Rotate keys in Dashboard if secrets were exposed.",
            "",
        ]
    )
    return "\n".join(lines)


def write_portfolio_report(data: dict[str, Any]) -> tuple[Path, Path]:
    reports = portfolio_reports_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = reports / f"portfolio-audit-{stamp}.json"
    md_path = reports / f"portfolio-audit-{stamp}.md"
    json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(data), encoding="utf-8")
    latest_md = reports / "LATEST.md"
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return md_path, json_path


def fix_webhooks_for_projects(
    owner_projects: list[Project],
    registry: list[PortfolioApp],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    by_slug = {p.slug: p for p in owner_projects}

    for app in registry:
        if app.stripe_exempt or not app.requires_stripe_webhook:
            continue
        if not app.project_slug or not app.webhook_url:
            continue
        project = by_slug.get(app.project_slug)
        if not project:
            results.append({"app": app.id, "ok": False, "message": f"No project slug {app.project_slug}"})
            continue
        root = project.local_path
        if not root:
            results.append({"app": app.id, "ok": False, "message": "project.local_path not set"})
            continue

        from pathlib import Path

        project_root = Path(root)
        if dry_run:
            results.append(
                {
                    "app": app.id,
                    "ok": True,
                    "dryRun": True,
                    "webhookUrl": app.webhook_url,
                }
            )
            continue

        try:
            secret = get_secret(project, "STRIPE_SECRET_KEY")
            if not secret:
                results.append({"app": app.id, "ok": False, "message": "STRIPE_SECRET_KEY not in vault"})
                continue
            cfg = ProvisionConfig(
                webhook_url=app.webhook_url,
                app_url=app.production_url or app.webhook_url.rsplit("/", 1)[0],
                create_webhook=True,
                create_portal=False,
                reuse_existing=True,
            )
            out = provision_catalog(
                secret,
                project_root,
                project=project,
                config=cfg,
            )
            results.append(
                {
                    "app": app.id,
                    "ok": True,
                    "webhookUrl": app.webhook_url,
                    "endpointId": (out.webhook_endpoint or {}).get("id"),
                    "webhookSecretStored": out.webhook_secret_stored,
                    "warnings": out.warnings,
                }
            )
        except Exception as exc:
            results.append({"app": app.id, "ok": False, "message": str(exc)})
    return results
