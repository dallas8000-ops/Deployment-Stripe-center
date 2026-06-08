"""AI copilot features — sanitized context only, never vault secrets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps.deploy.config import config_from_project, normalize_deploy_config
from apps.deploy.postgres import get_production_url
from apps.projects.models import Project
from apps.stripe_engine.diagnostics import DiagnosticReport, StripeIssue, run_diagnostics
from apps.stripe_engine.readiness import ReadinessCheck, run_readiness_checks, score_readiness
from apps.stripe_engine.repair import DEFAULT_CONFIG
from apps.stripe_engine.stripe_config import config_from_disk, normalize_stripe_config

from .chat import chat_with_ai, extract_json_block
from .services import _assert_safe


def _project_context(project: Project) -> str:
    scan = project.scan_data or {}
    return json.dumps(
        {
            "name": project.name,
            "framework": project.framework or scan.get("framework"),
            "language": project.language or scan.get("language"),
            "deployPlatform": scan.get("deployPlatform"),
            "productionUrl": get_production_url(project, ""),
            "localPathSet": bool(project.local_path),
        },
        indent=2,
    )


def _local_fix_explanation(issue: StripeIssue) -> dict[str, Any]:
    action = issue.fix_action or ""
    can_fix = issue.auto_fixable and bool(action)
    return {
        "issueId": issue.id,
        "title": issue.title,
        "explanation": (
            f"{issue.message} To resolve: {issue.fix_hint}"
            + (f" Click Apply fix to run `{action}` automatically." if can_fix else " Manual fix required.")
        ),
        "fixAction": action if can_fix else None,
        "autoFixable": can_fix,
        "severity": issue.severity,
    }


def fix_copilot(project: Project, report: DiagnosticReport | None = None) -> tuple[list[dict[str, Any]], str]:
    root = Path(project.local_path).resolve() if project.local_path else None
    if report is None:
        if not root or not root.is_dir():
            raise ValueError("Set project local_path and run diagnose first")
        report = run_diagnostics(project, root)

    issues_payload = [
        {
            "id": i.id,
            "title": i.title,
            "severity": i.severity,
            "category": i.category,
            "message": i.message,
            "fixHint": i.fix_hint,
            "autoFixable": i.auto_fixable,
            "fixAction": i.fix_action,
        }
        for i in report.issues
    ]
    _assert_safe(json.dumps(issues_payload))

    if not report.issues:
        return [], "local"

    try:
        prompt = (
            "You are a Stripe integration copilot. Explain each issue in plain language for a developer. "
            "Map auto-fixable issues to the exact fixAction slug provided. Never ask for API keys.\n\n"
            f"Project:\n{_project_context(project)}\n\n"
            f"Issues JSON:\n{json.dumps(issues_payload, indent=2)}\n\n"
            "Respond with ONLY a JSON array of objects: "
            '[{"issueId","explanation","fixAction","autoFixable","severity"}] '
            "One entry per issue, same order."
        )
        text, provider = chat_with_ai(project, prompt)
        parsed = extract_json_block(text) if text.strip().startswith("[") else json.loads(text)
        if isinstance(parsed, list):
            return parsed, provider
    except (RuntimeError, json.JSONDecodeError, ValueError):
        pass

    return [_local_fix_explanation(i) for i in report.issues], "local"


def readiness_coach(project: Project, checks: list[ReadinessCheck] | None = None) -> tuple[list[dict], str]:
    root = Path(project.local_path).resolve() if project.local_path else None
    if checks is None:
        if not root or not root.is_dir():
            raise ValueError("Set project local_path first")
        prod = get_production_url(project, "http://localhost:8000")
        checks = run_readiness_checks(project, root, production_url=prod)

    failing = [c for c in checks if c.status != "pass"]
    if not failing:
        return [], "local"

    payload = [c.to_dict() for c in failing]
    _assert_safe(json.dumps(payload))

    framework = project.framework or "unknown"
    try:
        prompt = (
            f"You are a production readiness coach for {framework} apps with Stripe. "
            "For each failing check, give framework-specific steps (exact files/paths where possible). "
            "Never ask for secrets.\n\n"
            f"Project:\n{_project_context(project)}\n\n"
            f"Checks:\n{json.dumps(payload, indent=2)}\n\n"
            'Respond ONLY with JSON array: [{"checkId","coachSteps","estimatedMinutes"}]'
        )
        text, provider = chat_with_ai(project, prompt)
        raw = text.strip()
        if raw.startswith("["):
            return json.loads(raw), provider
        return extract_json_block(text), provider
    except (RuntimeError, json.JSONDecodeError, ValueError):
        pass

    local = []
    for c in failing:
        steps = c.fix or c.message
        if framework == "nextjs" and "webhook" in c.id:
            steps += " — check app/api/stripe/webhook/route.ts and Vercel env vars."
        elif framework == "django" and "webhook" in c.id:
            steps += " — check stripe/urls.py and stripe/views.py webhook view."
        local.append({"checkId": c.id, "coachSteps": steps, "estimatedMinutes": 15})
    return local, "local"


def nl_to_configs(project: Project, instruction: str) -> tuple[dict, dict, str]:
    instruction = instruction.strip()
    if not instruction:
        raise ValueError("instruction is required")

    root = Path(project.local_path).resolve() if project.local_path else None
    stripe_base = config_from_disk(root) if root and root.is_dir() else normalize_stripe_config({})
    deploy_base = config_from_project(project, root) if root and root.is_dir() else normalize_deploy_config({})

    _assert_safe(instruction)

    prompt = (
        "Convert the user instruction into Stripe Installer config updates. "
        "Amounts are in cents (USD). Output ONLY JSON:\n"
        '{"stripeConfig":{"appUrl":"...","tiers":[{"name","amount","currency","interval","trialDays"}]},'
        '"deployConfig":{"productionUrl","platform","postgres":{"provider","autoProvision"}}}\n\n'
        f"Current stripe config:\n{json.dumps(stripe_base, indent=2)}\n\n"
        f"Current deploy config:\n{json.dumps(deploy_base, indent=2)}\n\n"
        f"User instruction:\n{instruction}"
    )

    try:
        text, provider = chat_with_ai(project, prompt, max_tokens=2500)
        data = extract_json_block(text)
        stripe_raw = {**stripe_base, **(data.get("stripeConfig") or {})}
        deploy_raw = {**deploy_base, **(data.get("deployConfig") or {})}
        return normalize_stripe_config(stripe_raw), normalize_deploy_config(deploy_raw), provider
    except RuntimeError:
        raise
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise ValueError(f"AI could not produce valid config: {exc}") from exc


def catalog_strategist(project: Project, business_description: str = "") -> tuple[dict, str, str]:
    desc = (business_description or project.description or "").strip()
    scan = project.scan_data or {}
    context = _project_context(project)

    try:
        prompt = (
            "Propose a SaaS pricing catalog for Stripe. Output ONLY JSON stripeConfig with appUrl and tiers "
            "(name, description, amount in cents, currency, interval month|year, trialDays, features array).\n\n"
            f"Project:\n{context}\n\nBusiness:\n{desc or 'General B2B SaaS'}\n\n"
            f"Detected features:\n{json.dumps(scan.get('recommendations', [])[:8])}"
        )
        text, provider = chat_with_ai(project, prompt)
        data = extract_json_block(text)
        cfg = normalize_stripe_config(data.get("stripeConfig", data))
        return cfg, text, provider
    except RuntimeError:
        pass

    cfg = normalize_stripe_config(DEFAULT_CONFIG)
    summary = "Using default Starter/Pro tiers — add ANTHROPIC_API_KEY or OPENAI_API_KEY for custom catalog."
    return cfg, summary, "local"


def handoff_pack(project: Project, *, production_url: str = "") -> tuple[dict[str, str], str]:
    prod = production_url or get_production_url(project, "https://your-app.example.com")
    scan = project.scan_data or {}
    framework = project.framework or "unknown"
    webhook_path = "/api/stripe/webhook" if framework in ("nextjs", "remix", "nuxt", "sveltekit") else "/stripe/webhook"
    webhook_url = f"{prod.rstrip('/')}{webhook_path}"

    template = {
        "prDescription": (
            f"## Stripe Installer setup\n\n"
            f"- Framework: **{framework}**\n"
            f"- Production URL: `{prod}`\n"
            f"- Webhook URL: `{webhook_url}`\n\n"
            f"Configure this webhook in Stripe Dashboard → Developers → Webhooks."
        ),
        "opsRunbook": (
            f"# Ops runbook — {project.name}\n\n"
            f"1. Set env vars from vault (never commit `.env.local`)\n"
            f"2. Webhook endpoint: {webhook_url}\n"
            f"3. Test card: 4242 4242 4242 4242\n"
            f"4. Stripe CLI: `stripe listen --forward-to localhost:3000{webhook_path}`\n"
            f"5. Billing portal return: {prod.rstrip('/')}/stripe/account/"
        ),
        "testChecklist": (
            "- [ ] Verify keys (test vs live mode)\n"
            "- [ ] Checkout with 4242 4242 4242 4242\n"
            "- [ ] Webhook receives checkout.session.completed\n"
            "- [ ] Customer linked in database\n"
            "- [ ] Billing portal opens\n"
            "- [ ] Subscription sync on customer.subscription.updated"
        ),
    }

    try:
        prompt = (
            "Generate a client handoff pack for a Stripe integration PR. "
            "Return ONLY JSON with keys prDescription (markdown), opsRunbook (markdown), testChecklist (markdown checklist).\n\n"
            f"Project:\n{_project_context(project)}\n\n"
            f"Webhook URL: {webhook_url}\n"
            f"Scan hints: {json.dumps(scan.get('recommendations', [])[:5])}"
        )
        text, provider = chat_with_ai(project, prompt, max_tokens=2500)
        data = extract_json_block(text)
        for key in ("prDescription", "opsRunbook", "testChecklist"):
            if key in data and isinstance(data[key], str):
                template[key] = data[key]
        _assert_safe(json.dumps(template))
        return template, provider
    except (RuntimeError, json.JSONDecodeError, ValueError):
        pass

    return template, "local"


def _event_preview_from_payload(payload: str) -> tuple[dict[str, Any], str]:
    stripped = payload.strip()
    if not stripped:
        raise ValueError("payload or event_id is required")

    _assert_safe(stripped)

    try:
        event = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    if not isinstance(event, dict):
        raise ValueError("payload must be a JSON object")

    data_obj = (event.get("data") or {}).get("object")
    safe_event = {
        "id": event.get("id"),
        "type": event.get("type"),
        "livemode": event.get("livemode"),
        "created": event.get("created"),
        "object_keys": list(data_obj.keys()) if isinstance(data_obj, dict) else [],
        "data": event.get("data"),
    }
    return safe_event, json.dumps(safe_event, indent=2)


def webhook_incident_assistant(
    project: Project,
    payload: str,
    *,
    fetched_from_stripe: bool = False,
) -> tuple[str, str]:
    """Analyze redacted webhook JSON — user must redact secrets before pasting."""
    safe_event, event_preview = _event_preview_from_payload(payload)

    framework = project.framework or "unknown"

    try:
        source = "fetched from Stripe API (sanitized)" if fetched_from_stripe else "user-pasted (must be redacted)"
        prompt = (
            f"You are a Stripe webhook debugging expert for {framework} apps. "
            "Explain: event type, what the handler should do, common failure modes, idempotency notes. "
            "Never ask for signing secrets.\n\n"
            f"Event source: {source}\n"
            f"Sanitized event:\n{event_preview}\n\n"
            f"Project:\n{_project_context(project)}"
        )
        return chat_with_ai(project, prompt)
    except RuntimeError:
        pass

    event_type = safe_event.get("type") or "unknown"
    local = (
        f"**Event type:** `{event_type}`\n\n"
        f"**Expected handler:** Dispatch to your webhook router, verify signature (server-side only), "
        f"then sync customer/subscription state to your database.\n\n"
        f"**Common failures:** Wrong webhook URL, stale STRIPE_WEBHOOK_SECRET, handler returns non-2xx, "
        f"raw body parsed before verify.\n\n"
        f"Add OPENAI_API_KEY or ANTHROPIC_API_KEY for deeper analysis."
    )
    return local, "local"
