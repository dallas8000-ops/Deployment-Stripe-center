"""Run compliance readiness checks (audit chain, retention config)."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.api_transfer.audit import verify_chain
from apps.projects.models import AuditLog


class Command(BaseCommand):
    help = "SOC 2 readiness checks: audit chain, retention settings, log counts"

    def handle(self, *args, **options):
        ok: list[str] = []
        warn: list[str] = []

        project_days = getattr(settings, "AUDIT_LOG_RETENTION_DAYS", 365)
        transfer_days = getattr(settings, "TRANSFER_AUDIT_RETENTION_DAYS", 2555)
        ok.append(f"AUDIT_LOG_RETENTION_DAYS={project_days}")
        ok.append(f"TRANSFER_AUDIT_RETENTION_DAYS={transfer_days}")

        chain = verify_chain()
        if chain.get("valid"):
            ok.append("Transfer audit hash chain valid")
        else:
            raise CommandError(f"Transfer audit chain broken at sequence {chain.get('brokenAt')}")

        audit_count = AuditLog.objects.count()
        ok.append(f"Project audit logs: {audit_count}")

        if not getattr(settings, "OIDC_SSO_ENABLED", False):
            warn.append("OIDC SSO disabled — enable for enterprise customers (deploy/OIDC-SSO.md)")
        if settings.DEBUG:
            warn.append("DJANGO_DEBUG=true — disable in production")

        for line in ok:
            self.stdout.write(self.style.SUCCESS(f"  OK   {line}"))
        for line in warn:
            self.stdout.write(self.style.WARNING(f"  WARN {line}"))

        self.stdout.write("\nSee deploy/COMPLIANCE.md and docs/compliance/ for full checklist.")
