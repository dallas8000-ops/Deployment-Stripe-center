"""Repair project workspace: real repo paths and vault keys from Automation Center hub."""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

HUB_SLUG = "stripe-installer"
STRIPE_KEYS = (
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
)
from apps.stripe_core.hub_keys import HUB_SHARED_DEPLOY_KEYS

VAULT_KEYS_FROM_HUB = STRIPE_KEYS + HUB_SHARED_DEPLOY_KEYS


class Command(BaseCommand):
    help = "Fix local_path to real repo folders and copy vault keys from hub"

    def add_arguments(self, parser):
        parser.add_argument("--project", action="append", dest="projects", help="Project slug (repeatable)")
        parser.add_argument("--all", action="store_true", help="Repair every non-hub project for the user")
        parser.add_argument(
            "--all-projects",
            action="store_true",
            help="Repair every non-hub project in the database (all owners)",
        )
        parser.add_argument("--user", default="", help="Owner email (default: first user)")
        parser.add_argument("--skip-vault", action="store_true", help="Only fix paths")
        parser.add_argument(
            "--remove-stale-workspaces",
            action="store_true",
            help="Delete legacy backend/clones and backend/clone* folders inside this hub",
        )

    def handle(self, *args, **options):
        from apps.diagnostics.diagnostics import run_diagnostics
        from apps.projects.models import Project
        from apps.stripe_core.portfolio_workspace import (
            is_invalid_portfolio_path,
            reconcile_hub_workspace,
            remove_stale_hub_workspaces,
            resolve_workspace_path,
        )
        from apps.vault.models import clear_project_vault, get_secret, set_secret, vault_health

        User = get_user_model()
        email = (options.get("user") or "").strip()
        owner = User.objects.get(email=email) if email else User.objects.first()
        if not owner:
            raise CommandError("No users found")

        slugs = options.get("projects") or []
        if options.get("all_projects"):
            project_qs = Project.objects.exclude(slug=HUB_SLUG)
        elif options.get("all"):
            project_qs = Project.objects.filter(owner=owner).exclude(slug=HUB_SLUG)
        elif slugs:
            project_qs = Project.objects.filter(slug__in=slugs).exclude(slug=HUB_SLUG)
        else:
            project_qs = Project.objects.none()

        if not project_qs.exists() and not options.get("remove_stale_workspaces"):
            raise CommandError("Pass --project <slug>, --all, --all-projects, or --remove-stale-workspaces")

        default_hub = Project.objects.filter(owner=owner, slug=HUB_SLUG).first()

        repaired = 0

        for project in project_qs:
            slug = project.slug

            before = (project.local_path or "").strip()
            path, changed = reconcile_hub_workspace(project)
            target_path = resolve_workspace_path(project) or path

            if changed or (before and is_invalid_portfolio_path(project, before)):
                repaired += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{slug}: local_path -> {path!r}"
                        + ("" if path else " (cleared — set your real app folder in Settings)")
                    )
                )
            elif target_path:
                self.stdout.write(f"{slug}: local_path already {path or target_path}")
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"{slug}: set local_path in Settings to your real app folder "
                        f"(e.g. C:\\Software Projects\\YourApp)"
                    )
                )

            if not options.get("skip_vault"):
                hub = (
                    Project.objects.filter(owner=project.owner, slug=HUB_SLUG).first()
                    or default_hub
                )
                if not hub:
                    self.stdout.write(self.style.WARNING(f"{slug}: hub project not found — skipped vault copy"))
                else:
                    health = vault_health(project)
                    if health["unreadableCount"]:
                        count = clear_project_vault(project)
                        self.stdout.write(
                            self.style.WARNING(f"{slug}: cleared {count} unreadable vault secret(s)")
                        )

                    copied: list[str] = []
                    for key in VAULT_KEYS_FROM_HUB:
                        if get_secret(project, key):
                            continue
                        value = get_secret(hub, key)
                        if value:
                            set_secret(project, key, value)
                            copied.append(key)

                    if copied:
                        self.stdout.write(self.style.SUCCESS(f"{slug}: copied vault keys — {', '.join(copied)}"))
                    elif not get_secret(project, "STRIPE_SECRET_KEY"):
                        self.stdout.write(self.style.WARNING(f"{slug}: STRIPE_SECRET_KEY still missing in vault"))

            root = Path(project.local_path or path or target_path)
            if root.is_dir():
                report = run_diagnostics(project, root.resolve())
                self.stdout.write(
                    f"{slug}: diagnose health {report.health_score}/100 — {report.summary}"
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"{slug}: open {target_path} in your editor and ensure the repo exists there")
                )

        if options.get("remove_stale_workspaces") or repaired:
            removed = remove_stale_hub_workspaces()
            if removed:
                self.stdout.write(self.style.SUCCESS(f"Removed stale hub workspace(s): {', '.join(removed)}"))
            else:
                self.stdout.write("No stale hub workspace folders found")

        if repaired:
            self.stdout.write(
                self.style.SUCCESS(f"\nRepaired {repaired} project(s) that pointed inside this hub repo")
            )
        self.stdout.write("\nWork in your app's real folder — this hub only runs setup against that path.")
