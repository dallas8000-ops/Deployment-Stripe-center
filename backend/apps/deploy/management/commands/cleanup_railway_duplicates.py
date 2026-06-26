"""Remove duplicate, orphan, and junk Railway services from hearty-enjoyment."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.env_push import _railway_environment_id, get_railway_env_vars
from apps.deploy.railway_consolidate import _find_project, _project_delete, _service_delete
from apps.deploy.railway_resolve import _list_railway_projects_with_domains
from apps.projects.models import Project
from apps.stripe_core.portfolio_catalog import PORTFOLIO_CATALOG
from apps.vault.models import get_secret

HOME_PROJECT_ID = "e5dce2f2-ffc6-4677-8f16-d3912934cebd"
HOME_PROJECT_NAME = "hearty-enjoyment"
KEEP_PROJECT_NAMES = frozenset({"agripay-logistics-ai", "hearty-enjoyment"})
STRIPE_JUNK_PROJECT_PREFIX = "stripe - "

# api + web (+ db) pairs — never treat as duplicates.
INTENTIONAL_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"dbops-api", "dbops-web"}),
    frozenset({"specwright-api", "specwright-web"}),
    frozenset({
        "elite-fintech-systems-api",
        "elite-fintech-systems-web",
        "elite-fintech-systems-db",
    }),
    frozenset({"righand", "righand-frontend"}),
)

# Older duplicate when both exist — delete the left name, keep the right.
KNOWN_DUPLICATE_PAIRS: tuple[tuple[str, str], ...] = (
    ("React-Store-Catalog", "React-Store-Catalog-1"),
    ("FrontLineDigital", "FrontLineDigital-1"),
    ("enpower-command-web", "EnPowerCommand"),
)

# Always remove from the monorepo canvas.
JUNK_SERVICE_NAMES = frozenset(
    {
        "token-probe-temp",
        "alert-perception",
        "postgres",  # orphan plugin — nothing references ${{Postgres.*}}
    }
)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _catalog_hosts() -> dict[str, str]:
    hosts: dict[str, str] = {}
    for entry in PORTFOLIO_CATALOG:
        if entry.get("merged"):
            continue
        url = str(entry.get("productionUrl") or "").strip()
        host = (urlparse(url).hostname or "").lower()
        slug = str(entry.get("projectSlug") or entry.get("id") or "").lower()
        if host and slug:
            hosts[slug] = host
        web = str(entry.get("webProductionUrl") or "").strip()
        web_host = (urlparse(web).hostname or "").lower()
        if web_host:
            hosts[f"{slug}:web"] = web_host
    return hosts


def _service_matches_catalog(svc: dict, catalog_hosts: dict[str, str]) -> bool:
    domains = [d.lower() for d in (svc.get("domains") or [])]
    if not domains:
        return False
    for host in catalog_hosts.values():
        if any(host in d or d.startswith(host.split(".")[0]) for d in domains):
            return True
    return False


def _orphan_postgres(token: str, home: dict) -> list[dict]:
    env_id = _railway_environment_id(token, home["id"])
    referenced: set[str] = set()
    for svc in home.get("services") or []:
        db = (get_railway_env_vars(token, home["id"], svc["id"], env_id).get("DATABASE_URL") or "").strip()
        if db.startswith("${{") and "." in db:
            plugin = db.split("{{", 1)[-1].split(".", 1)[0].strip().lower()
            if plugin:
                referenced.add(plugin)
    orphans: list[dict] = []
    for svc in home.get("services") or []:
        if (svc.get("name") or "").strip().lower() == "postgres":
            if "postgres" not in referenced:
                orphans.append(svc)
    return orphans


def _duplicate_stale_services(services: list[dict]) -> list[dict]:
    by_norm = {_norm(s.get("name")): s for s in services}
    stale: list[dict] = []
    for drop_name, keep_name in KNOWN_DUPLICATE_PAIRS:
        drop = next((s for s in services if _norm(s.get("name")) == _norm(drop_name)), None)
        keep = next((s for s in services if _norm(s.get("name")) == _norm(keep_name)), None)
        if drop and keep:
            stale.append(drop)
    return stale


class Command(BaseCommand):
    help = "Remove duplicate apps, orphan Postgres, test services, and Stripe junk projects."

    def add_arguments(self, parser):
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

        dry_run = options["dry_run"]
        if not dry_run and not options["confirm"]:
            raise CommandError("Pass --confirm to delete, or --dry-run to preview.")

        projects = _list_railway_projects_with_domains(token)
        home = next((p for p in projects if p["id"] == HOME_PROJECT_ID), None) or _find_project(
            projects, HOME_PROJECT_NAME
        )
        if not home:
            raise CommandError("hearty-enjoyment not found")

        services = home.get("services") or []
        catalog_hosts = _catalog_hosts()

        to_delete: list[dict] = []
        seen_ids: set[str] = set()

        def add(svc: dict, reason: str) -> None:
            sid = svc.get("id") or ""
            if sid and sid not in seen_ids:
                seen_ids.add(sid)
                to_delete.append({**svc, "_reason": reason})

        for svc in services:
            name = (svc.get("name") or "").strip()
            if name.lower() in JUNK_SERVICE_NAMES:
                add(svc, "orphan / test service")

        for svc in _orphan_postgres(token, home):
            add(svc, "unused Postgres plugin")

        for svc in _duplicate_stale_services(services):
            add(svc, "older duplicate (catalog points at sibling service)")

        self.stdout.write(self.style.MIGRATE_HEADING(f"{home['name']} — {len(services)} services"))
        if to_delete:
            self.stdout.write("Will remove:")
            for svc in to_delete:
                doms = ", ".join(svc.get("domains") or []) or "(no domain)"
                self.stdout.write(f"  [{svc['_reason']}] {svc.get('name')} | {doms}")
        else:
            self.stdout.write(self.style.SUCCESS("No duplicate services detected."))

        project_deletes: list[dict] = []
        for proj in projects:
            pname = (proj.get("name") or "").strip()
            if pname.lower() in KEEP_PROJECT_NAMES:
                continue
            svcs = proj.get("services") or []
            if not svcs or pname.lower().startswith(STRIPE_JUNK_PROJECT_PREFIX):
                project_deletes.append(proj)

        if project_deletes:
            self.stdout.write("")
            self.stdout.write("Will remove Railway project folders:")
            for proj in project_deletes:
                self.stdout.write(
                    f"  {proj.get('name')} ({len(proj.get('services') or [])} service(s))"
                )

        self.stdout.write("")
        self.stdout.write("Keeping (intentional pairs / catalog matches):")
        for svc in sorted(services, key=lambda x: (x.get("name") or "").lower()):
            sid = svc.get("id") or ""
            if sid in seen_ids:
                continue
            name = svc.get("name") or ""
            if _service_matches_catalog(svc, catalog_hosts):
                self.stdout.write(f"  {name} (catalog)")
            elif any(_norm(name) in {_norm(n) for n in group} for group in INTENTIONAL_GROUPS):
                self.stdout.write(f"  {name} (api/web pair)")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes made."))
            return

        for svc in to_delete:
            _service_delete(token, svc["id"])
            self.stdout.write(self.style.SUCCESS(f"Deleted {svc.get('name')}"))

        for proj in project_deletes:
            pname = proj.get("name") or ""
            for svc in proj.get("services") or []:
                _service_delete(token, svc["id"])
            _project_delete(token, proj["id"])
            self.stdout.write(self.style.SUCCESS(f"Deleted project {pname}"))

        try:
            refreshed = _list_railway_projects_with_domains(token)
            home = next((p for p in refreshed if p["id"] == HOME_PROJECT_ID), home)
            remaining = len(home.get("services") or [])
        except RuntimeError:
            remaining = len(services) - len(to_delete)
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Done — {remaining} services remain in hearty-enjoyment.")
        )