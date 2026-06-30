"""Validate environment for production go-live."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check production readiness (env vars, dev flags, optional SaaS/GitHub)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail if optional SaaS/GitHub billing vars are missing",
        )

    def handle(self, *args, **options):
        strict = options["strict"]
        errors: list[str] = []
        warnings: list[str] = []
        ok: list[str] = []

        def require(cond: bool, msg: str, *, warn_only: bool = False) -> None:
            if cond:
                ok.append(msg)
            elif warn_only:
                warnings.append(msg)
            else:
                errors.append(msg)

        require(not settings.DEBUG, "DJANGO_DEBUG is false")
        if getattr(settings, "PRODUCTION_SCALE", False):
            require(
                not settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("InMemoryChannelLayer"),
                "CHANNEL_LAYER_INMEMORY is false (Redis channel layer)",
            )
            redis_url = getattr(settings, "REDIS_URL", "")
            require(
                redis_url and "127.0.0.1" not in redis_url and "localhost" not in redis_url,
                "REDIS_URL points at managed Redis (not localhost)",
            )
        if not settings.DEBUG:
            require(
                getattr(settings, "SECURE_SSL_REDIRECT", False),
                "SECURE_SSL_REDIRECT enabled",
            )
            require(
                getattr(settings, "SESSION_COOKIE_SECURE", False),
                "SESSION_COOKIE_SECURE enabled",
            )
            require(
                getattr(settings, "CSRF_COOKIE_SECURE", False),
                "CSRF_COOKIE_SECURE enabled",
            )
            require(
                getattr(settings, "SECURE_HSTS_SECONDS", 0) > 0,
                "SECURE_HSTS_SECONDS configured",
            )
        django_secret = str(getattr(settings, "SECRET_KEY", "") or "")
        require(
            bool(django_secret)
            and django_secret
            not in {"change-me-in-production", "dev-only-change-me-in-production"},
            "DJANGO_SECRET_KEY is set (not default)",
        )
        require(bool(getattr(settings, "VAULT_MASTER_KEY", "")), "VAULT_MASTER_KEY is set")

        hosts = getattr(settings, "ALLOWED_HOSTS", [])
        require(
            hosts and hosts != ["*"] and "localhost" not in hosts,
            "DJANGO_ALLOWED_HOSTS set for production host(s)",
            warn_only=True,
        )

        db_url = getattr(settings, "DATABASE_URL", "") or ""
        require(
            db_url.startswith("postgres"),
            "DATABASE_URL uses PostgreSQL",
            warn_only=not db_url,
        )

        require(
            not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False),
            "CELERY_EAGER is false (worker required)",
        )

        inmemory = settings.CHANNEL_LAYERS["default"]["BACKEND"].endswith("InMemoryChannelLayer")
        require(not inmemory, "CHANNEL_LAYER_INMEMORY is false (Redis required)")

        redis_url = getattr(settings, "REDIS_URL", "")
        if redis_url and not inmemory:
            try:
                import redis

                redis.from_url(redis_url, socket_connect_timeout=2).ping()
                ok.append("Redis reachable")
            except Exception as exc:
                errors.append(f"Redis unreachable: {exc}")
        elif inmemory:
            warnings.append("Redis not checked (in-memory channel layer)")

        cors = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        require(
            cors and not any("localhost" in o for o in cors),
            "CORS_ALLOWED_ORIGINS uses production URL(s)",
            warn_only=True,
        )

        saas_key = getattr(settings, "SAAS_STRIPE_SECRET_KEY", "")
        if saas_key:
            ok.append("SAAS_STRIPE_SECRET_KEY configured")
            require(
                bool(getattr(settings, "SAAS_STRIPE_WEBHOOK_SECRET", "")),
                "SAAS_STRIPE_WEBHOOK_SECRET set",
                warn_only=not strict,
            )
            require(
                bool(getattr(settings, "SAAS_BILLING_RETURN_URL", "")),
                "SAAS_BILLING_RETURN_URL set",
                warn_only=not strict,
            )
        else:
            warnings.append("SAAS_STRIPE_SECRET_KEY not set (billing disabled)")

        gh_slug = getattr(settings, "GITHUB_APP_SLUG", "")
        if gh_slug:
            ok.append("GITHUB_APP_SLUG configured")
            require(
                bool(getattr(settings, "GITHUB_APP_ID", "")),
                "GITHUB_APP_ID set",
                warn_only=not strict,
            )
            require(
                bool(getattr(settings, "GITHUB_WEBHOOK_SECRET", "")),
                "GITHUB_WEBHOOK_SECRET set",
                warn_only=not strict,
            )
        else:
            warnings.append("GITHUB_APP_SLUG not set (GitHub App install disabled)")

        from pathlib import Path

        dist = Path(settings.BASE_DIR).parent / "frontend" / "dist"
        if dist.is_dir() and any(dist.iterdir()):
            ok.append("frontend/dist present")
        else:
            warnings.append("frontend/dist missing — run: npm run build:frontend")

        if getattr(settings, "LICENSE_ENFORCEMENT_ENABLED", False):
            ok.append("LICENSE_ENFORCEMENT_ENABLED is true")
            import os

            require(
                bool(os.environ.get("STRIPE_INSTALLER_LICENSE_KEY")),
                "STRIPE_INSTALLER_LICENSE_KEY set",
            )
            require(
                bool(os.environ.get("STRIPE_INSTALLER_DOMAIN")),
                "STRIPE_INSTALLER_DOMAIN set",
            )
            require(
                bool(
                    os.environ.get("STRIPE_INSTALLER_VALIDATION_SERVER")
                    or getattr(settings, "LICENSE_VALIDATION_SERVER", "")
                ),
                "STRIPE_INSTALLER_VALIDATION_SERVER set",
                warn_only=not strict,
            )
            try:
                from apps.licenses.service import license_status

                lic = license_status()
                require(lic.get("valid"), f"License valid ({lic.get('message', 'invalid')})")
            except Exception as exc:
                errors.append(f"License validation failed: {exc}")
        else:
            warnings.append("LICENSE_ENFORCEMENT_ENABLED is false (protection off)")

        for line in ok:
            self.stdout.write(self.style.SUCCESS(f"  OK  {line}"))
        for line in warnings:
            self.stdout.write(self.style.WARNING(f"  WARN  {line}"))
        for line in errors:
            self.stdout.write(self.style.ERROR(f"  FAIL  {line}"))

        if errors:
            self.stdout.write(self.style.ERROR(f"\n{len(errors)} error(s) — not production ready."))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("\nProduction checks passed."))
        if warnings:
            self.stdout.write(self.style.WARNING(f"{len(warnings)} warning(s) — review before go-live."))
