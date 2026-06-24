"""Verify deployment automation reliability — vault, env push readiness, metadata."""

from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.deploy.preflight import run_deploy_preflight
from apps.projects.models import Project
from apps.vault.master_key import master_key_path
from apps.vault.models import get_secret, vault_health


class Command(BaseCommand):
    help = "Audit vault health, master key stability, and Railway env push readiness for projects"

    def add_arguments(self, parser):
        parser.add_argument("--user", default="", help="Owner email (default: all users)")
        parser.add_argument("--project", action="append", dest="projects", help="Project slug (repeatable)")

    def handle(self, *args, **options):
        User = get_user_model()
        email = (options.get("user") or "").strip()
        slugs = options.get("projects") or []

        qs = Project.objects.all().order_by("slug")
        if email:
            qs = qs.filter(owner__email=email)
        if slugs:
            qs = qs.filter(slug__in=slugs)

        if not qs.exists():
            self.stdout.write(self.style.WARNING("No projects matched."))
            return

        self._check_master_key()
        issues = 0
        for project in qs:
            issues += self._check_project(project)

        if issues:
            self.stdout.write(self.style.ERROR(f"\n{issues} issue(s) found — fix before running deploy pipeline."))
        else:
            self.stdout.write(self.style.SUCCESS("\nAll checked projects look ready for deployment automation."))

    def _check_master_key(self) -> None:
        on_railway = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PUBLIC_DOMAIN"))
        env_key = os.environ.get("VAULT_MASTER_KEY", "").strip()
        file_key = master_key_path().read_text(encoding="utf-8").strip() if master_key_path().is_file() else ""

        if on_railway and not env_key:
            self.stdout.write(
                self.style.ERROR(
                    "CRITICAL: VAULT_MASTER_KEY not set on Railway — secrets will be lost on redeploy. "
                    "Add a permanent 64-char hex key to Railway Variables."
                )
            )
        elif on_railway and env_key:
            self.stdout.write(self.style.SUCCESS("Master key: VAULT_MASTER_KEY set in Railway environment"))
        elif file_key:
            self.stdout.write(self.style.SUCCESS(f"Master key: file at {master_key_path()}"))
            self.stdout.write(
                self.style.WARNING(
                    "  Railway production: run `python manage.py ensure_vault_master_key --show-key` "
                    "and paste VAULT_MASTER_KEY into Railway Variables (not auto-deployed from .env)"
                )
            )
        elif settings.VAULT_MASTER_KEY:
            self.stdout.write(self.style.SUCCESS("Master key: resolved from environment"))
        else:
            self.stdout.write(self.style.WARNING("Master key: not configured"))

    def _check_project(self, project: Project) -> int:
        self.stdout.write(f"\n=== {project.slug} ({project.name}) ===")
        issues = 0
        health = vault_health(project)

        if health["unreadableCount"]:
            issues += 1
            self.stdout.write(
                self.style.ERROR(
                    f"  Vault: {health['unreadableCount']}/{health['totalCount']} secret(s) unreadable — "
                    f"restore ~/.stripe-installer/projects/{project.slug}/vault.json or re-enter keys"
                )
            )
        elif health["totalCount"]:
            self.stdout.write(self.style.SUCCESS(f"  Vault: {health['totalCount']} secret(s), all readable"))
        else:
            self.stdout.write(self.style.WARNING("  Vault: empty — add keys before deploy"))

        if not project.local_path:
            issues += 1
            self.stdout.write(self.style.ERROR("  Workspace: local_path not set"))
        else:
            self.stdout.write(f"  Workspace: {project.local_path}")

        scan = project.scan_data or {}
        platform = scan.get("deployPlatform") or "unknown"
        if platform == "unknown":
            self.stdout.write(self.style.WARNING("  Platform: unknown — Railway auto env push will be skipped"))
        else:
            self.stdout.write(f"  Platform: {platform}")

        if platform == "railway":
            preflight = run_deploy_preflight(
                project,
                push_railway_env=True,
                provision_postgres=False,
                provision_stripe=project.slug != "stripe-installer"
                and not __import__(
                    "apps.stripe_core.portfolio_catalog",
                    fromlist=["is_stripe_exempt_slug"],
                ).is_stripe_exempt_slug(project.slug),
            )
            push_status = preflight.get("railway") or {}
            if not push_status.get("hasToken"):
                issues += 1
                self.stdout.write(self.style.ERROR("  Railway: RAILWAY_API_TOKEN missing from vault"))
            else:
                self.stdout.write(self.style.SUCCESS("  Railway: API token present"))

            project_id = push_status.get("resolvedProjectId") or push_status.get("storedProjectId")
            service_id = push_status.get("resolvedServiceId") or push_status.get("storedServiceId")
            if not project_id:
                issues += 1
                self.stdout.write(
                    self.style.ERROR(
                        "  Railway: project ID not resolved — set RAILWAY_PROJECT_ID in vault "
                        "or use a workspace token at railway.com/account/tokens"
                    )
                )
            else:
                self.stdout.write(f"  Railway project: {project_id}")

            if not service_id:
                issues += 1
                self.stdout.write(
                    self.style.ERROR(
                        "  Railway: web service ID not resolved — set RAILWAY_SERVICE_ID in vault"
                    )
                )
            else:
                self.stdout.write(f"  Railway service: {service_id}")

            railway = (project.scan_data or {}).get("railway") or {}
            if railway.get("lastEnvPushAt"):
                self.stdout.write(f"  Last env push: {railway['lastEnvPushAt']}")
            else:
                self.stdout.write(self.style.WARNING("  Last env push: never — run deploy or Push env vars"))

            for warning in preflight.get("warnings") or []:
                self.stdout.write(self.style.WARNING(f"  Note: {warning}"))

        stripe_key = get_secret(project, "STRIPE_SECRET_KEY")
        django_key = get_secret(project, "DJANGO_SECRET_KEY")
        if not stripe_key and project.slug != "stripe-installer":
            from apps.stripe_core.portfolio_catalog import is_stripe_exempt_slug

            if not is_stripe_exempt_slug(project.slug):
                issues += 1
                self.stdout.write(self.style.ERROR("  Stripe: STRIPE_SECRET_KEY missing"))
        if not django_key and scan.get("deployPlatform") == "railway":
            self.stdout.write(self.style.WARNING("  Django: DJANGO_SECRET_KEY missing — add before production deploy"))

        return issues
