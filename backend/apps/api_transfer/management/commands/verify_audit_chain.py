"""Verify API Transfer tamper-evident audit hash chain."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.api_transfer.audit import list_audit, verify_chain


class Command(BaseCommand):
    help = "Verify transfer audit log hash chain integrity"

    def handle(self, *args, **options):
        result = verify_chain()
        entries = len(list_audit())
        if result.get("valid"):
            self.stdout.write(self.style.SUCCESS(f"OK: {entries} audit entr(y/ies), chain valid"))
            return

        broken = result.get("brokenAt")
        raise CommandError(f"Audit chain broken at sequence {broken} ({entries} entries total)")
