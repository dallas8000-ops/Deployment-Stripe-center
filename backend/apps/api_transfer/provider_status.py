"""Provider readiness helpers for API Transfer endpoints."""

from __future__ import annotations

from django.conf import settings


def server_provider_config() -> dict:
    def _missing(*keys: str) -> list[str]:
        return [key for key in keys if not str(getattr(settings, key, "") or "").strip()]

    railway_missing = _missing("RAILWAY_API_TOKEN", "RAILWAY_PROJECT_ID")
    render_missing = list(_missing("RENDER_API_TOKEN"))
    render_deploy_ready = not _missing("RENDER_OWNER_ID")
    if not render_deploy_ready:
        render_missing.append("RENDER_OWNER_ID")

    return {
        "railway": {
            "configured": not railway_missing,
            "missing": railway_missing,
            "projectId": settings.RAILWAY_PROJECT_ID or None,
        },
        "render": {
            "configured": not _missing("RENDER_API_TOKEN"),
            "deployReady": render_deploy_ready,
            "missing": render_missing,
        },
        "stripe": {
            "configured": not _missing("STRIPE_SECRET_KEY"),
            "missing": _missing("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"),
        },
        "fly": {"configured": not _missing("FLY_API_TOKEN"), "missing": _missing("FLY_API_TOKEN")},
        "supabase": {
            "configured": not _missing("SUPABASE_ACCESS_TOKEN", "SUPABASE_ORG_ID"),
            "missing": _missing("SUPABASE_ACCESS_TOKEN", "SUPABASE_ORG_ID"),
        },
        "cloudflare": {
            "configured": not _missing("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZONE_ID"),
            "missing": _missing("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ZONE_ID"),
        },
        "github": {
            "configured": not _missing("GITHUB_TOKEN"),
            "missing": _missing("GITHUB_TOKEN"),
        },
        "vault": {
            "configured": bool(settings.VAULT_MASTER_KEY),
            "missing": [] if settings.VAULT_MASTER_KEY else ["VAULT_MASTER_KEY"],
        },
    }


def provider_live_status(provider: str) -> dict:
    matrix = {
        "fly": {
            "liveEnabled": bool(settings.FLY_API_TOKEN),
            "capabilities": ["discover", "deploy"],
            "message": "Live Fly.io deploy when FLY_API_TOKEN is configured.",
        },
        "github": {
            "liveEnabled": True,
            "capabilities": ["repo-import", "framework-detection"],
            "message": "Public repo import works without a token; private repos use GITHUB_TOKEN.",
        },
        "supabase": {
            "liveEnabled": bool(settings.SUPABASE_ACCESS_TOKEN and settings.SUPABASE_ORG_ID),
            "capabilities": ["discover", "database"],
            "message": "Live Supabase with access token and org id.",
        },
        "cloudflare": {
            "liveEnabled": bool(settings.CLOUDFLARE_API_TOKEN and settings.CLOUDFLARE_ZONE_ID),
            "capabilities": ["dns", "tls"],
            "message": "Live DNS with Cloudflare token and zone id.",
        },
        "stripe": {
            "liveEnabled": bool(settings.STRIPE_SECRET_KEY),
            "capabilities": ["billing", "webhooks"],
            "message": "Live Stripe when STRIPE_SECRET_KEY is configured.",
        },
        "terraform": {
            "liveEnabled": True,
            "capabilities": ["plan", "apply", "drift"],
            "message": "Terraform plan/apply runs inside the platform.",
        },
        "render": {
            "liveEnabled": bool(settings.RENDER_API_TOKEN),
            "capabilities": ["account-review", "discover", "deploy", "env-vars"],
            "message": "Live Render when RENDER_API_TOKEN is set (deploy also needs RENDER_OWNER_ID).",
        },
        "railway": {
            "liveEnabled": bool(settings.RAILWAY_API_TOKEN and settings.RAILWAY_PROJECT_ID),
            "capabilities": ["account-review", "discover", "deploy", "env-vars"],
            "message": "Live Railway when RAILWAY_API_TOKEN and RAILWAY_PROJECT_ID are set.",
        },
        "kong": {
            "liveEnabled": False,
            "capabilities": ["canonical-discovery"],
            "message": "Kong is planning-only.",
        },
        "orena": {
            "liveEnabled": bool(getattr(settings, "ORENA_API_TOKEN", "")),
            "capabilities": ["discover", "deploy", "regional"],
            "message": "Live Orena when ORENA_API_TOKEN is configured.",
        },
    }
    item = matrix.get(provider, {"liveEnabled": False, "capabilities": [], "message": "Unknown provider."})
    return {**item, "status": "live" if item["liveEnabled"] else "demo"}


def deployment_live_summary(result: dict) -> dict:
    stages = result.get("stages", [])
    live_stages = [s["stage"] for s in stages if s.get("data", {}).get("live") is True]
    simulated_stages = [s["stage"] for s in stages if s.get("data", {}).get("live") is False]
    return {
        "fullyLive": bool(live_stages) and not simulated_stages,
        "liveStages": live_stages,
        "simulatedStages": simulated_stages,
        "message": (
            "All provider-mutating stages ran live."
            if live_stages and not simulated_stages
            else "Some stages used safe simulation because provider credentials are not configured."
        ),
    }


def deploy_stage_data(result: dict) -> dict:
    stage = next((s for s in result.get("stages", []) if s.get("stage") == "deploy-app"), None)
    return (stage or {}).get("data", {})


def initial_deployment_status(result: dict) -> str:
    data = deploy_stage_data(result)
    if not data.get("live"):
        return "simulated"
    return "queued" if data.get("deployId") else "live"


def normalize_render_status(status: str) -> str:
    value = (status or "").strip().lower()
    if value in {"live", "succeeded", "success"}:
        return "live"
    if value in {"failed", "failure", "canceled", "cancelled"}:
        return "failed"
    if value in {"build_in_progress", "update_in_progress", "created", "queued", "pending"}:
        return "building"
    return value or "unknown"


def normalize_railway_status(status: str) -> str:
    value = (status or "").strip().upper()
    if value in {"SUCCESS", "ACTIVE"}:
        return "live"
    if value in {"FAILED", "CRASHED", "REMOVED", "SKIPPED"}:
        return "failed"
    if value in {"BUILDING", "DEPLOYING", "QUEUED", "WAITING", "INITIALIZING"}:
        return "building"
    return (status or "unknown").lower()
