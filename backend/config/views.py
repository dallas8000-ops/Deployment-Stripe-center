import os

from django.conf import settings
from django.http import JsonResponse


def _redis_check() -> tuple[str, bool]:
    """Return (status message, is_fatal_for_probe)."""
    eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
    inmemory = settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("InMemoryChannelLayer")
    if eager or inmemory:
        return "skipped (dev mode)", False
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.ping()
        return "ok", False
    except Exception as exc:
        fatal = bool(getattr(settings, "PRODUCTION_SCALE", False))
        return str(exc), fatal


def root(_request):
    return JsonResponse(
        {
            "service": "Deployment & Stripe Automation Center API",
            "status": "ok",
            "ui": getattr(settings, "APP_PUBLIC_URL", "http://localhost:5173"),
            "api": "/api/v1/",
        }
    )


def health(_request):
    checks: dict[str, str] = {}
    ok = True

    try:
        from django.db import connection

        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = str(exc)
        ok = False

    from apps.vault.master_key import vault_master_key_status

    vault_status = vault_master_key_status()
    if vault_status["stable"]:
        checks["vault"] = "ok"
    else:
        checks["vault"] = vault_status["detail"]
        ok = False

    if settings.DEBUG:
        checks["debug"] = "warning: DEBUG is true"
    else:
        checks["debug"] = "ok"

    eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
    inmemory = settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("InMemoryChannelLayer")
    redis_status, redis_fatal = _redis_check()
    checks["redis"] = redis_status
    if redis_fatal:
        ok = False
    if not eager and not inmemory:
        checks["celery"] = "worker not probed — ensure celery + beat services are running"
    elif eager or inmemory:
        checks["celery"] = "skipped (eager mode)"

    process_type = os.environ.get("PROCESS_TYPE", "web")
    checks["process_type"] = process_type

    from pathlib import Path

    dist = Path(settings.BASE_DIR).parent / "frontend" / "dist"
    checks["frontend_dist"] = "ok" if dist.is_dir() and any(dist.iterdir()) else "missing"

    checks["saas_billing"] = "configured" if getattr(settings, "SAAS_STRIPE_SECRET_KEY", "") else "disabled"
    checks["email"] = getattr(settings, "EMAIL_BACKEND", "").rsplit(".", 1)[-1]

    try:
        from apps.licenses.service import license_status

        lic = license_status()
        checks["license"] = "ok" if lic.get("valid") else lic.get("message", "invalid")
        if lic.get("enforcement") == "enabled" and not lic.get("valid"):
            ok = False
    except Exception as exc:
        checks["license"] = str(exc)

    from apps.core.api_revision import API_REVISION

    payload = {
        "status": "ok" if ok else "degraded",
        "version": getattr(settings, "APP_VERSION", "1.0.0"),
        "apiRevision": API_REVISION,
        "checks": checks,
    }
    return JsonResponse(payload, status=200 if ok else 503)


def readiness(_request):
    """Kubernetes/Railway readiness — DB + Redis required for scaled web replicas."""
    checks: dict[str, str] = {}
    ok = True

    try:
        from django.db import connection

        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = str(exc)
        ok = False

    redis_status, redis_fatal = _redis_check()
    checks["redis"] = redis_status
    if redis_fatal:
        ok = False

    payload = {
        "status": "ready" if ok else "not_ready",
        "process_type": os.environ.get("PROCESS_TYPE", "web"),
        "checks": checks,
    }
    return JsonResponse(payload, status=200 if ok else 503)


def metrics(_request):
    """Basic ops metrics — DB/Redis latency, queue depth, webhook volume."""
    from apps.diagnostics.ops_metrics import collect_ops_metrics

    return JsonResponse(collect_ops_metrics())
