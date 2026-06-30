"""Audit Stripe and deploy secrets — vault, Stripe endpoints, Railway, live webhook route."""

from __future__ import annotations

import ssl
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import stripe

from apps.deploy.env_push import get_railway_env_vars
from apps.projects.models import Project
from apps.stripe_core.hub_keys import (
    HUB_SLUG,
    get_hub_project,
    resolve_expected_webhook_url,
)
from apps.stripe_core.portfolio_catalog import is_stripe_exempt_slug
from apps.stripe_core.verify import verify_stripe_keys
from apps.vault.import_env import ENV_FILE_CANDIDATES
from apps.vault.app_secrets import parse_env_file
from apps.vault.models import get_secret, vault_health


@dataclass
class PlacementIssue:
    severity: str  # error | warning | info
    layer: str  # vault | stripe | railway | live | local
    code: str
    message: str
    fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SecretPlacementReport:
    projectSlug: str
    projectName: str
    stripeExempt: bool
    expectedWebhookUrl: str | None = None
    vault: dict[str, Any] = field(default_factory=dict)
    stripeEndpoint: dict[str, Any] | None = None
    railway: dict[str, Any] | None = None
    liveProbe: dict[str, Any] | None = None
    localEnv: dict[str, Any] | None = None
    issues: list[PlacementIssue] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [i.to_dict() if isinstance(i, PlacementIssue) else i for i in self.issues]
        return payload


def _fingerprint(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return "missing"
    if len(text) < 12:
        return "too_short"
    return f"{text[:10]}…{text[-4:]}"


def _key_format(key: str, value: str | None) -> tuple[bool, str]:
    text = (value or "").strip()
    if not text:
        return False, "missing"
    if key == "STRIPE_SECRET_KEY":
        if text.startswith("sk_"):
            return True, "sk_ok"
        return False, "expected sk_ prefix"
    if key in ("STRIPE_WEBHOOK_SECRET", "SAAS_STRIPE_WEBHOOK_SECRET"):
        if text.startswith("whsec_"):
            return True, "whsec_ok"
        if text.startswith("sk_"):
            return False, "wrong type — sk_ in webhook secret slot"
        return False, "expected whsec_ prefix"
    if key == "STRIPE_PUBLISHABLE_KEY":
        if text.startswith("pk_"):
            return True, "pk_ok"
        return False, "expected pk_ prefix"
    return bool(text), "present"


def _normalize_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


def _hub_webhook_env_keys(project: Project) -> tuple[str, ...]:
    if project.slug == HUB_SLUG:
        return ("SAAS_STRIPE_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET")
    return ("STRIPE_WEBHOOK_SECRET",)


def _read_local_stripe_env(local_path: str) -> dict[str, str]:
    from pathlib import Path

    root = Path(local_path)
    if not root.is_dir():
        return {}
    found: dict[str, str] = {}
    for name in ENV_FILE_CANDIDATES:
        path = root / name
        if not path.is_file():
            continue
        try:
            found.update(parse_env_file(path))
        except OSError:
            continue
    return {
        k: v
        for k, v in found.items()
        if k.startswith("STRIPE_") or k.startswith("SAAS_STRIPE_") or k.startswith("NEXT_PUBLIC_STRIPE_")
    }


def _probe_webhook_post(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    normalized = url if url.endswith("/") else f"{url}/"
    for attempt_url in (normalized, normalized.rstrip("/")):
        try:
            req = Request(
                attempt_url,
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "stripe-installer-secret-audit/1.0"},
            )
            ctx = ssl.create_default_context()
            with urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read(300).decode("utf-8", errors="replace")
                return {
                    "url": attempt_url,
                    "httpStatus": resp.status,
                    "bodySnippet": body[:120],
                    "reachable": True,
                }
        except HTTPError as exc:
            body = exc.read(300).decode("utf-8", errors="replace") if exc.fp else ""
            return {
                "url": attempt_url,
                "httpStatus": exc.code,
                "bodySnippet": body[:120],
                "reachable": True,
            }
        except URLError as exc:
            last_error = str(getattr(exc, "reason", exc))
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
    return {"url": url, "httpStatus": None, "bodySnippet": "", "reachable": False, "error": last_error}


def _classify_live_probe(status: int | None, body: str) -> str:
    if status is None:
        return "unreachable"
    snippet = (body or "").lower()
    if status == 403 and "csrf" in snippet:
        return "csrf_blocked"
    if status == 404:
        return "route_missing"
    if status == 405:
        return "method_not_allowed"
    if status == 503:
        return "not_configured"
    if status == 400 and ("invalid payload" in snippet or "signature" in snippet or "stripe" in snippet):
        return "signature_check_active"
    if status == 400:
        return "bad_request"
    if 200 <= status < 300:
        return "ok"
    return "unknown"


def audit_project_secret_placement(
    project: Project,
    *,
    hub: Project | None = None,
    check_railway: bool = True,
    check_live: bool = True,
    check_local: bool = True,
) -> SecretPlacementReport:
    """Verify secrets exist in vault, Stripe, Railway, and live route for one project."""
    report = SecretPlacementReport(
        projectSlug=project.slug,
        projectName=project.name,
        stripeExempt=is_stripe_exempt_slug(project.slug),
    )
    issues: list[PlacementIssue] = []

    if report.stripeExempt:
        health = vault_health(project)
        report.vault = {"totalCount": health["totalCount"], "unreadableCount": health["unreadableCount"]}
        if health["unreadableCount"]:
            issues.append(
                PlacementIssue(
                    "warning",
                    "vault",
                    "vault_unreadable",
                    f"{health['unreadableCount']} vault secret(s) unreadable",
                    "Restore vault backup or re-enter keys",
                )
            )
        report.issues = issues
        report.ok = not any(i.severity == "error" for i in issues)
        return report

    if hub is None:
        hub = get_hub_project(project.owner)

    health = vault_health(project)
    sk = get_secret(project, "STRIPE_SECRET_KEY")
    pk = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
    wh = get_secret(project, "STRIPE_WEBHOOK_SECRET")
    if project.slug == HUB_SLUG and not wh:
        wh = get_secret(project, "SAAS_STRIPE_WEBHOOK_SECRET")

    vault_keys: dict[str, Any] = {}
    for key, value in (
        ("STRIPE_SECRET_KEY", sk),
        ("STRIPE_PUBLISHABLE_KEY", pk),
        ("STRIPE_WEBHOOK_SECRET", wh),
    ):
        ok_fmt, fmt = _key_format(key, value)
        vault_keys[key] = {"fingerprint": _fingerprint(value), "formatOk": ok_fmt, "format": fmt}
        if not ok_fmt:
            issues.append(
                PlacementIssue(
                    "error",
                    "vault",
                    f"vault_{key.lower()}",
                    f"Vault {key}: {fmt}",
                    "Run Setup Hub register webhooks or paste correct key in Vault",
                )
            )

    if health["unreadableCount"]:
        issues.append(
            PlacementIssue(
                "error",
                "vault",
                "vault_unreadable",
                f"{health['unreadableCount']} vault secret(s) unreadable",
                "Restore ~/.stripe-installer/projects backup or re-enter keys",
            )
        )

    if hub and project.slug != HUB_SLUG and wh:
        hub_wh = get_secret(hub, "STRIPE_WEBHOOK_SECRET") or get_secret(hub, "SAAS_STRIPE_WEBHOOK_SECRET")
        if hub_wh and wh == hub_wh:
            issues.append(
                PlacementIssue(
                    "error",
                    "vault",
                    "webhook_secret_shared_with_hub",
                    "Child project uses the hub webhook signing secret — each app needs its own whsec_",
                    "Run register webhooks for this project (do not copy hub whsec to child apps)",
                )
            )

    if sk and pk:
        verification = verify_stripe_keys(sk, pk)
        vault_keys["stripeApiVerified"] = verification.secret_key.valid
        if not verification.secret_key.valid:
            issues.append(
                PlacementIssue(
                    "error",
                    "vault",
                    "stripe_api_invalid",
                    verification.secret_key.message,
                    "Update STRIPE_SECRET_KEY in vault from Stripe Dashboard → Developers → API keys",
                )
            )

    report.vault = {"health": health, "keys": vault_keys}

    expected = resolve_expected_webhook_url(project) or None
    report.expectedWebhookUrl = expected

    if sk and expected:
        stripe.api_key = sk
        try:
            endpoints = stripe.WebhookEndpoint.list(limit=100).data
        except stripe.StripeError as exc:
            issues.append(
                PlacementIssue(
                    "error",
                    "stripe",
                    "stripe_list_failed",
                    str(exc),
                    "Check STRIPE_SECRET_KEY in vault",
                )
            )
            endpoints = []

        normalized_expected = _normalize_url(expected)
        matches = [ep for ep in endpoints if _normalize_url(ep.url) == normalized_expected]
        host_dupes = [
            ep
            for ep in endpoints
            if _normalize_url(ep.url) != normalized_expected
            and (ep.url or "").split("//")[-1].split("/")[0]
            == expected.split("//")[-1].split("/")[0]
        ]

        report.stripeEndpoint = {
            "expectedUrl": expected,
            "matchCount": len(matches),
            "endpointIds": [ep.id for ep in matches],
            "duplicateHostCount": len(host_dupes),
        }

        if not matches:
            issues.append(
                PlacementIssue(
                    "error",
                    "stripe",
                    "stripe_endpoint_missing",
                    f"No Stripe webhook endpoint for {expected}",
                    "Run Setup Hub → Register webhooks",
                )
            )
        for ep in host_dupes:
            issues.append(
                PlacementIssue(
                    "warning",
                    "stripe",
                    "stripe_duplicate_host",
                    f"Extra webhook on same host: {ep.url}",
                    "Delete stale endpoint in Stripe Dashboard",
                )
            )

    if check_railway:
        railway_info: dict[str, Any] = {"keys": {}}
        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        scan = project.scan_data or {}
        platform = scan.get("deployPlatform") or "unknown"

        if platform == "unknown" and project.local_path:
            from pathlib import Path

            from apps.deploy.platform import detect_deploy_platform

            root = Path(project.local_path)
            if root.is_dir():
                platform = detect_deploy_platform(root, project.framework)

        railway_info["platform"] = platform

        if platform != "railway":
            railway_info["skipped"] = "platform_not_railway"
        elif not token:
            issues.append(
                PlacementIssue(
                    "warning",
                    "railway",
                    "railway_token_missing",
                    "RAILWAY_API_TOKEN not in vault — cannot compare Railway env",
                    "Add token on hub project vault, then sync",
                )
            )
        else:
            from apps.deploy.railway_resolve import (
                resolve_railway_project_id,
                resolve_railway_web_service_id,
            )

            project_id = (get_secret(project, "RAILWAY_PROJECT_ID") or "").strip()
            service_id = (get_secret(project, "RAILWAY_SERVICE_ID") or "").strip()
            if not project_id:
                project_id = resolve_railway_project_id(project, token) or ""
            if project_id and not service_id:
                service_id = resolve_railway_web_service_id(project, token, project_id) or ""

            if not project_id or not service_id:
                issues.append(
                    PlacementIssue(
                        "warning",
                        "railway",
                        "railway_target_unresolved",
                        "Railway project/service ID not resolved",
                        "Set RAILWAY_PROJECT_ID and RAILWAY_SERVICE_ID in vault",
                    )
                )
            else:
                from apps.deploy.env_push import _railway_environment_id

                try:
                    env_id = _railway_environment_id(token, project_id)
                    remote = get_railway_env_vars(token, project_id, service_id, env_id)
                except Exception as exc:  # noqa: BLE001
                    remote = {}
                    issues.append(
                        PlacementIssue(
                            "warning",
                            "railway",
                            "railway_fetch_failed",
                            str(exc),
                            "Verify RAILWAY_API_TOKEN and service IDs",
                        )
                    )

                railway_info["projectId"] = project_id
                railway_info["serviceId"] = service_id

                compare_keys = [
                    ("STRIPE_SECRET_KEY", sk),
                    ("STRIPE_PUBLISHABLE_KEY", pk),
                ]
                for env_key in _hub_webhook_env_keys(project):
                    compare_keys.append((env_key, wh))

                for env_key, vault_val in compare_keys:
                    remote_val = (remote.get(env_key) or "").strip()
                    entry = {
                        "vault": _fingerprint(vault_val),
                        "railway": _fingerprint(remote_val),
                        "match": bool(vault_val and remote_val and vault_val == remote_val),
                    }
                    railway_info["keys"][env_key] = entry
                    if vault_val and not remote_val:
                        issues.append(
                            PlacementIssue(
                                "error",
                                "railway",
                                f"railway_{env_key.lower()}_missing",
                                f"Railway service missing {env_key} (vault has value)",
                                "Run Push env vars or Setup Hub bootstrap",
                            )
                        )
                    elif vault_val and remote_val and vault_val != remote_val:
                        issues.append(
                            PlacementIssue(
                                "error",
                                "railway",
                                f"railway_{env_key.lower()}_mismatch",
                                f"Railway {env_key} does not match vault",
                                "Push vault to Railway or update vault from Stripe Dashboard signing secret",
                            )
                        )

                if project.slug == HUB_SLUG:
                    saas_wh = remote.get("SAAS_STRIPE_WEBHOOK_SECRET", "").strip()
                    stripe_wh = remote.get("STRIPE_WEBHOOK_SECRET", "").strip()
                    handler_reads = "SAAS_STRIPE_WEBHOOK_SECRET"
                    if wh and not saas_wh and stripe_wh == wh:
                        issues.append(
                            PlacementIssue(
                                "warning",
                                "railway",
                                "hub_saas_webhook_alias",
                                "Hub Railway has STRIPE_WEBHOOK_SECRET but billing handler reads SAAS_STRIPE_WEBHOOK_SECRET",
                                "Push env again — hub deploy now mirrors SAAS_* aliases",
                            )
                        )
                    elif wh and not saas_wh and not stripe_wh:
                        issues.append(
                            PlacementIssue(
                                "error",
                                "railway",
                                "hub_webhook_env_missing",
                                f"Hub Railway missing {handler_reads} for billing webhook",
                                "Push vault secrets to Railway",
                            )
                        )

        report.railway = railway_info

    if check_live and expected:
        probe = _probe_webhook_post(expected)
        probe["classification"] = _classify_live_probe(probe.get("httpStatus"), probe.get("bodySnippet", ""))
        report.liveProbe = probe
        classification = probe["classification"]
        if classification == "csrf_blocked":
            issues.append(
                PlacementIssue(
                    "error",
                    "live",
                    "webhook_csrf",
                    f"POST {expected} blocked by CSRF (HTTP {probe.get('httpStatus')})",
                    "Add csrf_exempt webhook route at this exact path in the app code",
                )
            )
        elif classification == "route_missing":
            issues.append(
                PlacementIssue(
                    "error",
                    "live",
                    "webhook_404",
                    f"Webhook route not found at {expected}",
                    "Deploy app code with matching webhook path or fix portfolio registry URL",
                )
            )
        elif classification == "unreachable":
            issues.append(
                PlacementIssue(
                    "error",
                    "live",
                    "webhook_unreachable",
                    f"Could not reach {expected}: {probe.get('error', 'unknown')}",
                    "Check Railway service is online and URL in portfolio registry",
                )
            )
        elif classification == "signature_check_active":
            pass  # expected for unsigned probe — secrets likely wired if not 403/404
        elif classification not in ("ok", "bad_request", "not_configured"):
            issues.append(
                PlacementIssue(
                    "warning",
                    "live",
                    "webhook_probe",
                    f"Unexpected probe response HTTP {probe.get('httpStatus')}",
                    "Inspect deployed webhook handler",
                )
            )

    if check_local and project.local_path:
        local = _read_local_stripe_env(project.local_path)
        report.localEnv = {k: _fingerprint(v) for k, v in local.items()}
        if wh:
            local_wh = local.get("STRIPE_WEBHOOK_SECRET") or local.get("SAAS_STRIPE_WEBHOOK_SECRET")
            if local_wh and local_wh != wh:
                issues.append(
                    PlacementIssue(
                        "warning",
                        "local",
                        "local_env_webhook_drift",
                        "Local .env webhook secret differs from hub vault",
                        "Treat vault + Railway as source of truth; update or remove stale .env values",
                    )
                )
            if local_wh and local_wh.startswith("sk_"):
                issues.append(
                    PlacementIssue(
                        "error",
                        "local",
                        "local_env_wrong_webhook_type",
                        "Local .env has sk_ in STRIPE_WEBHOOK_SECRET",
                        "Replace with whsec_ from Stripe Dashboard for this endpoint URL",
                    )
                )

    report.issues = issues
    report.ok = not any(i.severity == "error" for i in issues)
    return report


def audit_portfolio_secret_placement(user, **kwargs: Any) -> dict[str, Any]:
    from apps.core.access import projects_for_user

    hub = get_hub_project(user)
    projects = list(projects_for_user(user).order_by("slug"))
    reports = [
        audit_project_secret_placement(project, hub=hub, **kwargs).to_dict()
        for project in projects
        if not is_stripe_exempt_slug(project.slug)
    ]
    billing = [r for r in reports if not r.get("stripeExempt")]
    return {
        "ok": all(r.get("ok") for r in billing),
        "projectCount": len(reports),
        "errorCount": sum(
            1 for r in billing for i in (r.get("issues") or []) if i.get("severity") == "error"
        ),
        "projects": reports,
    }


def repair_project_secret_placement(project: Project, *, hub: Project | None = None) -> dict[str, Any]:
    """Re-register webhooks, store whsec_, push vault → Railway for one billing project."""
    from pathlib import Path

    from apps.deploy.env_push import try_auto_push_railway_stripe_env
    from apps.stripe_core.portfolio_audit import fix_webhooks_for_projects
    from apps.stripe_core.portfolio_registry import load_registry

    if is_stripe_exempt_slug(project.slug):
        return {"ok": True, "skipped": True, "message": "Stripe exempt"}

    if not project.local_path or not Path(project.local_path).is_dir():
        return {"ok": False, "message": "local_path missing or not a directory"}

    registry = load_registry()
    fixes = fix_webhooks_for_projects([project], registry, dry_run=False)
    row = fixes[0] if fixes else {"ok": False, "message": "No webhook fix result"}
    env_push = try_auto_push_railway_stripe_env(project) or {}
    audit = audit_project_secret_placement(project, hub=hub).to_dict()
    return {
        "ok": bool(row.get("ok")) and bool(env_push.get("ok", True)) and audit.get("ok"),
        "webhook": row,
        "envPush": env_push,
        "audit": audit,
    }
