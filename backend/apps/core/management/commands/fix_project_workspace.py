"""Repair project workspace: clone path, git checkout, vault keys from Automation Center hub."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

HUB_SLUG = "stripe-installer"
STRIPE_KEYS = (
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
)
from apps.stripe_installer.hub_keys import HUB_SHARED_DEPLOY_KEYS

VAULT_KEYS_FROM_HUB = STRIPE_KEYS + HUB_SHARED_DEPLOY_KEYS


class Command(BaseCommand):
    help = "Fix local_path, clone repo, and copy Stripe vault keys from the Automation Center hub project"

    def add_arguments(self, parser):
        parser.add_argument("--project", action="append", dest="projects", help="Project slug (repeatable)")
        parser.add_argument("--user", default="", help="Owner email (default: first user)")
        parser.add_argument("--skip-clone", action="store_true", help="Only fix paths and vault")
        parser.add_argument("--skip-vault", action="store_true", help="Only fix paths and clone")

    def handle(self, *args, **options):
        from apps.diagnostics.diagnostics import run_diagnostics
        from apps.projects.git_clone import clone_project_repo
        from apps.projects.models import Project
        from apps.vault.models import clear_project_vault, get_secret, set_secret, vault_health

        User = get_user_model()
        email = (options.get("user") or "").strip()
        owner = User.objects.get(email=email) if email else User.objects.first()
        if not owner:
            raise CommandError("No users found")

        slugs = options.get("projects") or []
        if not slugs:
            raise CommandError("Pass --project <slug> (e.g. --project elite-fintech-systems --project righand)")

        hub = Project.objects.filter(owner=owner, slug=HUB_SLUG).first()
        if not hub and not options.get("skip_vault"):
            raise CommandError(f"Hub project {HUB_SLUG} not found for this user")

        from apps.stripe_installer.portfolio_workspace import resolve_workspace_path

        clone_root = Path(getattr(settings, "PROJECT_CLONE_ROOT", settings.BASE_DIR / "clones"))

        for slug in slugs:
            try:
                project = Project.objects.get(owner=owner, slug=slug)
            except Project.DoesNotExist as exc:
                self.stdout.write(self.style.ERROR(f"Unknown project: {slug}"))
                continue

            # Prefer the real portfolio repo folder; only fall back to hub clones when no catalog path exists.
            target_path = resolve_workspace_path(project) or str((clone_root / slug).resolve())
            if project.local_path != target_path:
                project.local_path = target_path
                project.save(update_fields=["local_path", "updated_at"])
                self.stdout.write(self.style.SUCCESS(f"{slug}: local_path -> {target_path}"))
            else:
                self.stdout.write(f"{slug}: local_path already {target_path}")

            if not options.get("skip_clone"):
                if not project.git_url:
                    self.stdout.write(self.style.WARNING(f"{slug}: no git_url — set in project settings"))
                else:
                    try:
                        out = clone_project_repo(project, force=False)
                        self.stdout.write(self.style.SUCCESS(f"{slug}: git {out['action']} -> {out['local_path']}"))
                    except Exception as exc:
                        self.stdout.write(self.style.ERROR(f"{slug}: clone failed — {exc}"))

            if not options.get("skip_vault") and hub:
                health = vault_health(project)
                if health["unreadableCount"]:
                    count = clear_project_vault(project)
                    self.stdout.write(
                        self.style.WARNING(f"{slug}: cleared {count} unreadable vault secret(s) (DB + local backup)")
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
                    self.stdout.write(self.style.SUCCESS(f"{slug}: copied vault keys from hub — {', '.join(copied)}"))
                elif not get_secret(project, "STRIPE_SECRET_KEY"):
                    self.stdout.write(
                        self.style.WARNING(
                            f"{slug}: STRIPE_SECRET_KEY still missing — add keys in Vault UI on "
                            f"{HUB_SLUG} or {slug}"
                        )
                    )

            root = Path(project.local_path)
            if root.is_dir():
                report = run_diagnostics(project, root.resolve())
                self.stdout.write(
                    f"{slug}: diagnose health {report.health_score}/100 — {report.summary}"
                )
            else:
                self.stdout.write(self.style.WARNING(f"{slug}: clone directory missing — run clone again"))

        self.stdout.write("\nNext: open each project in the app -> Verify keys -> Run full setup")
