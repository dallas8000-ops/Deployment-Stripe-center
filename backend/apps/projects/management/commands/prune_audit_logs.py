"""Prune project audit logs older than AUDIT_LOG_RETENTION_DAYS."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.projects.models import AuditLog


class Command(BaseCommand):
    help = "Delete project AuditLog rows older than AUDIT_LOG_RETENTION_DAYS (default 365)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count rows without deleting")
        parser.add_argument("--days", type=int, default=0, help="Override retention days")

    def handle(self, *args, **options):
        days = options["days"] or getattr(settings, "AUDIT_LOG_RETENTION_DAYS", 365)
        cutoff = timezone.now() - timedelta(days=days)
        qs = AuditLog.objects.filter(created_at__lt=cutoff)
        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(f"dry-run: would delete {count} project audit log(s) older than {days} days")
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"deleted {deleted} project audit log(s) (retention={days}d)"))
