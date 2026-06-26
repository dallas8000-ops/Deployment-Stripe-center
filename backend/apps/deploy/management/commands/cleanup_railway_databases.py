"""Remove orphan / duplicate database services from a Railway monorepo project."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.railway_consolidate import _find_project, _service_delete
from apps.deploy.railway_resolve import _list_railway_projects_with_domains
from apps.projects.models import Project
from apps.vault.models import get_secret

# Orphan / test services safe to remove from hearty-enjoyment during AgriPay cleanup.
CLEANUP_SERVICE_NAMES = frozenset(
    {
        "postgres-agripay",
        "agripay-logistics-ai",
        "agripay-logistics-ai-production",
        "token-probe-temp",
    }
)


class Command(BaseCommand):
    help = (
        "Delete orphan AgriPay database/web leftovers in hearty-enjoyment "
        "(Postgres-AgriPay, token-probe-temp, stale AgriPay-Logistics-AI)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--project-id", default="e5dce2f2-ffc6-4677-8f16-d3912934cebd")
        parser.add_argument("--project-name", default="hearty-enjoyment")
        parser.add_argument("--slug", default="agripay-logistics-ai", help="Hub slug for Railway token")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **options):
        slug = options["slug"].strip().lower()
        try:
            project = Project.objects.get(slug=slug)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project '{slug}' not found") from exc

        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        if not token:
            raise CommandError("RAILWAY_API_TOKEN missing from vault")

        projects = _list_railway_projects_with_domains(token)
        home_id = options["project_id"].strip()
        home = next((p for p in projects if p["id"] == home_id), None)
        if not home:
            home = _find_project(projects, options["project_name"])
        if not home:
            raise CommandError("hearty-enjoyment project not found")

        self.stdout.write(self.style.MIGRATE_HEADING(f"{home['name']} ({home['id']})"))
        candidates: list[dict] = []
        for svc in home.get("services") or []:
            name = (svc.get("name") or "").strip()
            norm = name.lower()
            if norm in CLEANUP_SERVICE_NAMES or norm.startswith("postgres-agripay"):
                candidates.append(svc)

        if not candidates:
            self.stdout.write(self.style.SUCCESS("No orphan AgriPay/database services to remove."))
            self._list_postgres(home)
            return

        for svc in candidates:
            doms = ", ".join(svc.get("domains") or []) or "(no domain)"
            self.stdout.write(f"  DELETE: {svc.get('name')} | {svc.get('id')} | {doms}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no changes made."))
            return
        if not options["confirm"]:
            raise CommandError("Pass --confirm to delete, or --dry-run to preview.")

        for svc in candidates:
            _service_delete(token, svc["id"])
            self.stdout.write(self.style.SUCCESS(f"Deleted {svc.get('name')}"))

        self.stdout.write("")
        self._list_postgres(home)

    def _list_postgres(self, home: dict) -> None:
        self.stdout.write("Postgres services remaining in project:")
        for svc in sorted(home.get("services") or [], key=lambda x: (x.get("name") or "").lower()):
            if "postgres" in (svc.get("name") or "").lower():
                self.stdout.write(f"  {svc.get('name')} ({svc.get('id')})")
