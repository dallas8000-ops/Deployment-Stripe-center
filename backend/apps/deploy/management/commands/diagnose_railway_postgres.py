"""Diagnose Railway Postgres wiring for a portfolio project (no secrets printed)."""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.env_push import (
    _railway_environment_id,
    get_railway_env_vars,
    is_placeholder_database_url,
    is_railway_reference,
)
from apps.deploy.postgres import test_postgres_connection
from apps.deploy.railway_postgres import postgres_service_for_preset
from apps.deploy.railway_resolve import (
    _list_railway_services,
    resolve_railway_project_id,
    resolve_railway_web_service_id,
)
from apps.projects.models import Project
from apps.vault.models import get_secret


def _redact_db_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return "(empty)"
    if is_railway_reference(text):
        return text
    return re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", text)


class Command(BaseCommand):
    help = "Check Railway Postgres service + DATABASE_URL for a hub project slug."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Hub project slug, e.g. agripay-logistics-ai")

    def handle(self, *args, **options):
        slug = options["slug"].strip().lower()
        try:
            project = Project.objects.get(slug=slug)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project '{slug}' not found") from exc

        expected_postgres = postgres_service_for_preset(slug)

        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        if not token:
            raise CommandError("RAILWAY_API_TOKEN missing from vault")

        project_id = resolve_railway_project_id(project, token)
        if not project_id:
            raise CommandError("Could not resolve Railway project ID")

        web_service_id = resolve_railway_web_service_id(project, token, project_id)
        if not web_service_id:
            raise CommandError("Could not resolve Railway web service ID")

        env_id = _railway_environment_id(token, project_id)
        services = _list_railway_services(token, project_id)
        postgres_services = [s for s in services if "postgres" in (s.get("name") or "").lower()]
        web_services = [s for s in services if "postgres" not in (s.get("name") or "").lower()]

        self.stdout.write(f"\n=== Railway Postgres diagnose: {slug} ===\n")
        self.stdout.write(f"Project ID: {project_id}")
        self.stdout.write(f"Web service ID: {web_service_id}")
        self.stdout.write(f"Environment ID: {env_id}\n")

        self.stdout.write("Services in project:")
        for svc in services:
            role = "postgres" if svc in postgres_services else "web/other"
            self.stdout.write(f"  - {svc.get('name')} ({svc.get('id')}) [{role}]")

        if not postgres_services:
            self.stdout.write(self.style.ERROR("\nISSUE: No Postgres plugin service found in this project."))
            self.stdout.write("Add Postgres in Railway, then set DATABASE_URL=${{Postgres.DATABASE_URL}} on the web service.")
        else:
            names = [s["name"] for s in postgres_services]
            self.stdout.write(self.style.SUCCESS(f"\nPostgres plugin(s): {', '.join(names)}"))
            if not any(n.lower() == "postgres" for n in names):
                hint = (
                    "Hub preset uses ${{Postgres.DATABASE_URL}} — rename plugin or update --postgres-service."
                )
                if expected_postgres:
                    hint = f"Hub automation expects Postgres plugin '{expected_postgres}' for this app."
                self.stdout.write(self.style.WARNING(f"WARNING: No service named exactly 'Postgres'. {hint}"))

        web_vars = get_railway_env_vars(token, project_id, web_service_id, env_id)
        db_url = (web_vars.get("DATABASE_URL") or "").strip()
        self.stdout.write(f"\nWeb service DATABASE_URL: {_redact_db_url(db_url)}")

        if not db_url:
            self.stdout.write(self.style.ERROR("ISSUE: DATABASE_URL missing on web service."))
        elif is_railway_reference(db_url):
            self.stdout.write(self.style.SUCCESS("DATABASE_URL is a Railway reference (correct pattern)."))
            match = re.match(r"\$\{\{(.+?)\.DATABASE_URL\}\}", db_url)
            ref_name = match.group(1) if match else "?"
            if postgres_services and ref_name not in [s["name"] for s in postgres_services]:
                self.stdout.write(
                    self.style.ERROR(
                        f"ISSUE: Reference points to '{ref_name}' but project has: {[s['name'] for s in postgres_services]}"
                    )
                )
        elif is_placeholder_database_url(db_url):
            self.stdout.write(self.style.ERROR("ISSUE: DATABASE_URL looks like a placeholder/localhost URL."))
        else:
            self.stdout.write("DATABASE_URL is a literal postgres URL — testing connection…")
            conn = test_postgres_connection(db_url)
            if conn["ok"]:
                self.stdout.write(self.style.SUCCESS(f"  {conn['message']}"))
                self._inspect_schema(db_url)
            else:
                self.stdout.write(self.style.ERROR(f"  Connection failed: {conn['message']}"))

        vault_db = (get_secret(project, "DATABASE_URL") or "").strip()
        if vault_db:
            self.stdout.write(f"\nVault DATABASE_URL: {_redact_db_url(vault_db)}")
            if vault_db.startswith(("postgres://", "postgresql://")) and is_railway_reference(db_url):
                self.stdout.write(
                    self.style.WARNING(
                        "Vault has literal postgres URL but Railway uses reference — "
                        "Railway runtime uses service variables, not vault."
                    )
                )

    def _inspect_schema(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError:
            self.stdout.write("  (psycopg not installed — skip schema inspect)")
            return
        try:
            with psycopg.connect(database_url, connect_timeout=10, sslmode="require") as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT name FROM django_migrations WHERE app = %s ORDER BY name",
                        ["accounts"],
                    )
                    rows = [r[0] for r in cur.fetchall()]
                    cur.execute(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                        ["accounts_farmerprofile"],
                    )
                    farmer_exists = bool(cur.fetchone()[0])
                    cur.execute(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
                        ["accounts_user"],
                    )
                    user_exists = bool(cur.fetchone()[0])
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Schema inspect failed: {exc}"))
            return

        self.stdout.write(f"  accounts migrations recorded: {rows or '(none)'}")
        self.stdout.write(f"  accounts_user exists: {user_exists}")
        self.stdout.write(f"  accounts_farmerprofile exists: {farmer_exists}")
        if "0001_initial" in rows and not farmer_exists:
            self.stdout.write(
                self.style.ERROR(
                    "  ISSUE: Schema drift — 0001_initial recorded but accounts_farmerprofile missing. "
                    "Run repair_accounts_schema on deploy (or reset Postgres)."
                )
            )
        elif farmer_exists and "0002_reconciliation_and_personal_collection" not in rows:
            self.stdout.write(
                self.style.WARNING(
                    "  0002 not applied yet — next deploy migrate should add collection_tier."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("  Schema/migration state looks consistent for accounts."))
