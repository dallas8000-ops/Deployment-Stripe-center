from django.conf import settings
from django.http import JsonResponse


def root(_request):
    return JsonResponse(
        {
            "service": "Stripe Installer SaaS API",
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

    if settings.VAULT_MASTER_KEY:
        checks["vault"] = "ok"
    else:
        checks["vault"] = "VAULT_MASTER_KEY not set"
        ok = False

    if settings.DEBUG:
        checks["debug"] = "warning: DEBUG is true"
    else:
        checks["debug"] = "ok"

    eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
    inmemory = settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("InMemoryChannelLayer")
    if not eager and not inmemory:
        try:
            import redis

            client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            client.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = str(exc)
            # Railway single-container deploys run without Redis — don't fail the probe.
            if not getattr(settings, "ON_RAILWAY", False):
                ok = False
    else:
        checks["redis"] = "skipped (dev mode)"
        checks["celery"] = "skipped (eager mode)"

    if not eager and not inmemory:
        checks["celery"] = "worker not probed — ensure celery + beat are running"

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

    payload = {
        "status": "ok" if ok else "degraded",
        "version": getattr(settings, "APP_VERSION", "1.0.0"),
        "checks": checks,
    }
    return JsonResponse(payload, status=200 if ok else 503)
