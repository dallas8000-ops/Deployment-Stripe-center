"""Remove AgriPay leftovers from hearty-enjoyment and delete empty Railway projects."""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.env_push import _railway_environment_id, get_railway_env_vars
from apps.deploy.railway_consolidate import _find_project, _project_delete, _service_delete
from apps.deploy.railway_resolve import _list_railway_projects_with_domains
from apps.projects.models import Project
from apps.vault.models import get_secret

HOME_PROJECT_ID = "e5dce2f2-ffc6-4677-8f16-d3912934cebd"
HOME_PROJECT_NAME = "hearty-enjoyment"

# Keep the real AgriPay stack in its own Railway project — never delete that project here.
KEEP_PROJECT_NAMES = frozenset({"agripay-logistics-ai", "hearty-enjoyment"})

# Stripe Projects provisioning experiments — safe to remove when user consolidates folders.
STRIPE_JUNK_PROJECT_PREFIX = "stripe - "


def _is_agripay_service_in_monorepo(name: str, domains: list[str]) -> bool:
    norm = (name or "").strip().lower()
    if not norm:
        return False
    if "agripay" in norm:
        return True
    if norm.startswith("postgres-agripay"):
        return True
    for domain in domains:
        d = (domain or "").lower()
        if "agripay" in d:
            return True
    return False


def _orphan_postgres_in_home(token: str, home: dict) -> list[dict]:
    """Generic Postgres plugin with no ${{Postgres.*}} consumers in the monorepo."""
    env_id = _railway_environment_id(token, home["id"])
    referenced: set[str] = set()
    for svc in home.get("services") or []:
        vars_map = get_railway_env_vars(token, home["id"], svc["id"], env_id)
        db = (vars_map.get("DATABASE_URL") or "").strip()
        if db.startswith("${{") and "." in db:
            plugin = db.split("{{", 1)[-1].split(".", 1)[0].strip()
            if plugin:
                referenced.add(plugin.lower())

    orphans: list[dict] = []
    for svc in home.get("services") or []:
        name = (svc.get("name") or "").strip()
        norm = name.lower()
        if norm != "postgres":
            continue
        if norm not in referenced and name.lower() not in referenced:
            orphans.append(svc)
    return orphans


class Command(BaseCommand):
    help = (
        "Delete AgriPay web/Postgres duplicates from hearty-enjoyment, remove orphan "
        "Postgres plugins, test services, Stripe junk projects, and empty Railway folders."
    )

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="agripay-logistics-ai")
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
        home = next((p for p in projects if p["id"] == HOME_PROJECT_ID), None) or _find_project(
            projects, HOME_PROJECT_NAME
        )
        if not home:
            raise CommandError("hearty-enjoyment not found")

        dry_run = options["dry_run"]
        if not dry_run and not options["confirm"]:
            raise CommandError("Pass --confirm to apply changes, or --dry-run to preview.")

        self.stdout.write(self.style.MIGRATE_HEADING(f"Scanning {home['name']}"))

        service_deletes: list[dict] = []
        for svc in home.get("services") or []:
            name = svc.get("name") or ""
            domains = svc.get("domains") or []
            if _is_agripay_service_in_monorepo(name, domains):
                service_deletes.append(svc)
            elif (name or "").strip().lower() == "token-probe-temp":
                service_deletes.append(svc)

        for svc in _orphan_postgres_in_home(token, home):
            if svc not in service_deletes:
                service_deletes.append(svc)

        if service_deletes:
            self.stdout.write("Services to remove from hearty-enjoyment:")
            for svc in service_deletes:
                doms = ", ".join(svc.get("domains") or []) or "(no domain)"
                self.stdout.write(f"  {svc.get('name')} | {svc.get('id')} | {doms}")
        else:
            self.stdout.write(self.style.SUCCESS("No AgriPay/orphan services in hearty-enjoyment."))

        project_deletes: list[dict] = []
        for proj in projects:
            pname = (proj.get("name") or "").strip()
            if pname.lower() in KEEP_PROJECT_NAMES:
                continue
            svcs = proj.get("services") or []
            if not svcs:
                project_deletes.append(proj)
                continue
            if pname.lower().startswith(STRIPE_JUNK_PROJECT_PREFIX):
                project_deletes.append(proj)

        if project_deletes:
            self.stdout.write("")
            self.stdout.write("Railway project folders to remove:")
            for proj in project_deletes:
                svcs = proj.get("services") or []
                self.stdout.write(
                    f"  {proj.get('name')} | {proj.get('id')} | {len(svcs)} service(s)"
                )
        else:
            self.stdout.write(self.style.SUCCESS("No empty or Stripe junk project folders found."))

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes made."))
            return

        for svc in service_deletes:
            _service_delete(token, svc["id"])
            self.stdout.write(self.style.SUCCESS(f"Deleted service: {svc.get('name')}"))

        for proj in project_deletes:
            pname = proj.get("name") or ""
            for svc in proj.get("services") or []:
                _service_delete(token, svc["id"])
                self.stdout.write(self.style.SUCCESS(f"Deleted service: {svc.get('name')} ({pname})"))
            _project_delete(token, proj["id"])
            self.stdout.write(self.style.SUCCESS(f"Deleted project: {pname}"))

        projects = _list_railway_projects_with_domains(token)
        for proj in projects:
            pname = (proj.get("name") or "").strip()
            if pname.lower() in KEEP_PROJECT_NAMES:
                continue
            if not (proj.get("services") or []):
                _project_delete(token, proj["id"])
                self.stdout.write(self.style.SUCCESS(f"Deleted empty project: {pname}"))

        self.stdout.write("")
        self.stdout.write("Postgres services still in hearty-enjoyment:")
        home = next((p for p in projects if p["id"] == HOME_PROJECT_ID), home)
        for svc in sorted(home.get("services") or [], key=lambda x: (x.get("name") or "").lower()):
            if re.search(r"postgres", (svc.get("name") or ""), re.I):
                self.stdout.write(f"  {svc.get('name')} ({svc.get('id')})")
