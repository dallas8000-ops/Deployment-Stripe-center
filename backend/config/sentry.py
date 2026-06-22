"""Sentry initialization — Django, Celery, Redis, and logging."""

from __future__ import annotations

import logging
import os

_initialized = False


def init_sentry() -> bool:
    global _initialized
    if _initialized:
        return True

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    debug = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0")),
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development" if debug else "production"),
        release=os.environ.get("APP_VERSION", "1.0.0"),
        send_default_pii=False,
    )
    _initialized = True
    return True
