"""Remove merged legacy Project rows (e.g. elite-fintech-web → elite-fintech-systems)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.projects.models import Project
from apps.stripe_installer.portfolio_catalog import MERGED_INTO_PROJECT_SLUGS, is_merged_legacy_slug


class Command(BaseCommand):
    help = "Delete merged legacy hub projects after confirming canonical slug exists"

    def add_arguments(self, parser):
        parser.add_argument("--user", default="", help="Owner email (default: first user)")
        parser.add_argument("--dry-run", action="store_true", help="Show actions only")

    def handle(self, *args, **options):
        User = get_user_model()
        email = (options.get("user") or "").strip()
        owner = User.objects.get(email=email) if email else User.objects.first()
        if not owner:
            raise CommandError("No users found")

        dry_run = bool(options.get("dry_run"))
        removed = 0

        for legacy_slug, canonical_slug in MERGED_INTO_PROJECT_SLUGS.items():
            if not is_merged_legacy_slug(legacy_slug):
                continue
            legacy = Project.objects.filter(owner=owner, slug=legacy_slug).first()
            if not legacy:
                continue
            canonical = Project.objects.filter(owner=owner, slug=canonical_slug).first()
            if not canonical:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skip {legacy_slug}: canonical project '{canonical_slug}' not found"
                    )
                )
                continue
            if dry_run:
                self.stdout.write(f"Would delete merged project: {legacy_slug} → use {canonical_slug}")
            else:
                legacy.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted merged project: {legacy_slug}"))
            removed += 1

        if removed == 0:
            self.stdout.write("No merged legacy projects to purge")
        elif dry_run:
            self.stdout.write(f"Dry run — {removed} project(s) would be removed")
