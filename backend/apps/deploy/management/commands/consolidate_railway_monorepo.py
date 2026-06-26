"""Move a portfolio app from a standalone Railway project into hearty-enjoyment."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.railway_consolidate import consolidate_agripay_to_monorepo
from apps.projects.models import Project
from apps.vault.models import get_secret


class Command(BaseCommand):
    help = (
        "Consolidate AgriPay into the shared hearty-enjoyment Railway project: "
        "delete the disconnected copy, recreate the working web + Postgres there, "
        "migrate the database, and remove the standalone project."
    )

    def add_arguments(self, parser):
        parser.add_argument("slug", default="agripay-logistics-ai", nargs="?")
        parser.add_argument("--home-project", default="hearty-enjoyment")
        parser.add_argument("--source-project", default="agripay-logistics-ai")
        parser.add_argument("--repo", default="", help="GitHub owner/repo (auto-detected from source)")
        parser.add_argument("--branch", default="main")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--skip-db-copy", action="store_true")
        parser.add_argument("--keep-source-project", action="store_true")
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required for live changes (deletes services and standalone project)",
        )

    def handle(self, *args, **options):
        slug = (options["slug"] or "agripay-logistics-ai").strip().lower()
        try:
            project = Project.objects.get(slug=slug)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project '{slug}' not found") from exc

        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        if not token:
            raise CommandError("RAILWAY_API_TOKEN missing from vault")

        if not options["dry_run"] and not options["confirm"]:
            raise CommandError("Pass --confirm to run live consolidation (or --dry-run to preview)")

        result = consolidate_agripay_to_monorepo(
            project,
            token,
            home_project_name=options["home_project"],
            source_project_name=options["source_project"],
            repo=options["repo"],
            branch=options["branch"],
            dry_run=options["dry_run"],
            skip_db_copy=options["skip_db_copy"],
            delete_source_project=not options["keep_source_project"],
        )

        if result.get("dryRun"):
            self.stdout.write(self.style.MIGRATE_HEADING("Dry run — no changes made"))
            plan = result["plan"]
            self.stdout.write(f"Home: {plan['homeProject']} ({plan['homeProjectId']})")
            self.stdout.write(f"Source: {plan['sourceProject']} ({plan['sourceProjectId']})")
            dup = plan.get("deleteDuplicate")
            if dup:
                self.stdout.write(f"Would delete duplicate: {dup['name']} ({dup['id']})")
            self.stdout.write(
                f"Would create: {plan['newPostgresName']} + {plan['newWebName']} in {plan['homeProject']}"
            )
            self.stdout.write(f"Repo: {plan['repo']}@{plan['branch']}")
            return

        self.stdout.write(self.style.SUCCESS(result.get("message", "Done")))
        if result.get("deletedDuplicate"):
            self.stdout.write(f"Removed duplicate: {result['deletedDuplicate']}")
        if result.get("deletedSourceProject"):
            self.stdout.write(f"Removed standalone project: {result['deletedSourceProject']}")
        self.stdout.write(result.get("dashboardUrl", ""))
        if result.get("deploymentId"):
            self.stdout.write(f"Deploy: {result['deploymentId']}")
