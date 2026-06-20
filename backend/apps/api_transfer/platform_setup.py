"""Platform credential audit and safe verify actions (Automation Center)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from .provider_status import provider_live_status, server_provider_config
from .providers import ProviderApiError, list_railway_services, list_render_services


def _missing(*keys: str) -> list[str]:
    return [key for key in keys if not str(getattr(settings, key, "") or "").strip()]


def audit_platform(*, scan_railway_stripe: bool = False) -> dict[str, Any]:
    """Return setup tasks based on configured provider credentials."""
    del scan_railway_stripe  # reserved for future Railway env scan
    config = server_provider_config()
    tasks: list[dict[str, Any]] = []
    needs_attention = 0

    checks = [
        ("railway", "Railway", ["RAILWAY_API_TOKEN", "RAILWAY_PROJECT_ID"]),
        ("render", "Render", ["RENDER_API_TOKEN", "RENDER_OWNER_ID"]),
        ("github", "GitHub", ["GITHUB_TOKEN"]),
        ("stripe", "Stripe (platform)", ["STRIPE_SECRET_KEY"]),
        ("fly", "Fly.io", ["FLY_API_TOKEN"]),
        ("supabase", "Supabase", ["SUPABASE_ACCESS_TOKEN", "SUPABASE_ORG_ID"]),
        ("cloudflare", "Cloudflare", ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZONE_ID"]),
        ("vault", "Vault master key", []),
    ]

    for key, label, env_keys in checks:
        block = config.get(key, {})
        missing = block.get("missing") or _missing(*env_keys)
        if key == "vault":
            missing = [] if block.get("configured") else ["VAULT_MASTER_KEY"]
        if key == "vault":
            live = {
                "status": "live" if not missing else "demo",
                "message": "Vault master key for encrypted project secrets.",
            }
        else:
            live = provider_live_status(key)

        status = "ready" if not missing and (
            block.get("configured") or block.get("deployReady") or key == "vault"
        ) else ("partial" if missing and env_keys and len(missing) < len(env_keys) else "missing")
        if status != "ready":
            needs_attention += 1

        issues = []
        if missing:
            issues.append(
                {
                    "id": f"{key}-credentials",
                    "severity": "high" if key in {"railway", "stripe"} else "medium",
                    "title": f"{label} credentials incomplete",
                    "detail": f"Missing: {', '.join(missing)}",
                    "resolution": f"Add keys to private_env/ or project vault. Never commit real values.",
                    "autoFixable": False,
                }
            )

        auto_actions = []
        if not missing or key in {"railway", "render", "github"}:
            auto_actions.append({"id": f"verify_{key}", "label": f"Test {label} API"})

        tasks.append(
            {
                "id": key,
                "service": label,
                "title": f"{label} setup",
                "status": status,
                "category": "foundation",
                "issues": issues,
                "autoActions": auto_actions,
                "liveStatus": live.get("status"),
                "liveMessage": live.get("message", ""),
            }
        )

    return {
        "summary": {
            "needsAttention": needs_attention,
            "taskCount": len(tasks),
            "readyCount": sum(1 for t in tasks if t["status"] == "ready"),
        },
        "tasks": tasks,
        "serverConfig": config,
    }


def run_setup_action(action_id: str) -> dict[str, Any]:
    """Run a safe, read-only or idempotent setup action."""
    handlers = {
        "verify_railway": _verify_railway,
        "verify_render": _verify_render,
        "verify_github": _verify_github,
        "verify_stripe": _verify_stripe,
        "verify_fly": _verify_fly,
        "verify_all_providers": _verify_all,
    }
    handler = handlers.get(action_id)
    if handler is None:
        return {"ok": False, "actionId": action_id, "message": f"Unknown action '{action_id}'."}
    try:
        result = handler()
        result["ok"] = True
        result["actionId"] = action_id
        return result
    except ProviderApiError as exc:
        return {"ok": False, "actionId": action_id, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "actionId": action_id, "message": str(exc)}


def _verify_railway() -> dict[str, Any]:
    if not settings.RAILWAY_API_TOKEN:
        return {"message": "RAILWAY_API_TOKEN is not configured."}
    services = list_railway_services(settings.RAILWAY_PROJECT_ID or None)
    return {"message": f"Railway OK — {len(services)} service(s) visible.", "count": len(services)}


def _verify_render() -> dict[str, Any]:
    if not settings.RENDER_API_TOKEN:
        return {"message": "RENDER_API_TOKEN is not configured."}
    services = list_render_services(limit=20)
    return {"message": f"Render OK — {len(services)} service(s) visible.", "count": len(services)}


def _verify_github() -> dict[str, Any]:
    token = settings.GITHUB_TOKEN
    if not token:
        return {"message": "GITHUB_TOKEN not set — public repo import still works."}
    return {"message": "GitHub token is configured."}


def _verify_stripe() -> dict[str, Any]:
    if not settings.STRIPE_SECRET_KEY:
        return {"message": "STRIPE_SECRET_KEY is not configured."}
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    account = stripe.Account.retrieve()
    return {"message": f"Stripe OK — account {account.get('id', '')}.", "accountId": account.get("id")}


def _verify_fly() -> dict[str, Any]:
    if not settings.FLY_API_TOKEN:
        return {"message": "FLY_API_TOKEN is not configured."}
    return {"message": "Fly token is configured (deploy not exercised in verify)."}


def _verify_all() -> dict[str, Any]:
    results = {
        "railway": _verify_railway(),
        "render": _verify_render(),
        "github": _verify_github(),
        "stripe": _verify_stripe(),
        "fly": _verify_fly(),
    }
    return {"message": "Provider verification complete.", "results": results}
