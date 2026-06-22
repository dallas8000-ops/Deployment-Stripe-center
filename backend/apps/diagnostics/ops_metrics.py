"""Lightweight ops metrics for health dashboards and on-call."""

from __future__ import annotations

import os
import time
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count
from django.utils import timezone


def collect_ops_metrics() -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "timestamp": timezone.now().isoformat(),
        "version": getattr(settings, "APP_VERSION", "1.0.0"),
        "process_type": os.environ.get("PROCESS_TYPE", "web"),
        "debug": settings.DEBUG,
        "production_scale": getattr(settings, "PRODUCTION_SCALE", False),
        "celery_eager": getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False),
    }

    try:
        from django.db import connection

        start = time.perf_counter()
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        metrics["database_ms"] = round((time.perf_counter() - start) * 1000, 2)
        metrics["database"] = "ok"
    except Exception as exc:
        metrics["database"] = str(exc)

    inmemory = settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("InMemoryChannelLayer")
    if inmemory:
        metrics["redis"] = "skipped (in-memory channel layer)"
    else:
        try:
            import redis

            start = time.perf_counter()
            client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            client.ping()
            metrics["redis_ms"] = round((time.perf_counter() - start) * 1000, 2)
            metrics["redis"] = "ok"
        except Exception as exc:
            metrics["redis"] = str(exc)

    since = timezone.now() - timedelta(hours=24)
    try:
        from apps.billing.models import BillingWebhookEvent

        metrics["billing_webhooks_24h"] = BillingWebhookEvent.objects.filter(
            processed_at__gte=since
        ).count()
    except Exception:
        metrics["billing_webhooks_24h"] = None

    try:
        from apps.api_transfer.models import TransferRun

        metrics["transfer_runs"] = {
            status: count
            for status, count in TransferRun.objects.values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        }
        metrics["transfer_queue_depth"] = TransferRun.objects.filter(
            status__in=(
                TransferRun.STATUS_QUEUED,
                TransferRun.STATUS_RETRYABLE,
                TransferRun.STATUS_RUNNING,
            )
        ).count()
    except Exception:
        metrics["transfer_runs"] = {}
        metrics["transfer_queue_depth"] = None

    metrics["sentry_enabled"] = bool(os.environ.get("SENTRY_DSN", "").strip())
    return metrics
