"""Push vault + preset env vars to Railway (SilverFox, Kistie, etc.)."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.env_push import auto_push_railway_env, build_env_var_payload
from apps.deploy.railway_postgres import postgres_service_for_preset
from apps.deploy.railway_resolve import (
    preset_for_project,
    remember_railway_targets,
    resolve_railway_project_id,
    resolve_railway_web_service_id,
)
from apps.projects.models import Project
from apps.vault.models import get_secret, set_secret


class Command(BaseCommand):
    help = (
        "Push hub vault secrets + preset to Railway. "
        "One-time: pass --project-id and --service-id (from Railway dashboard) to store in vault."
    )

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Hub project slug (e.g. silverfox)")
        parser.add_argument("--preset", default="", help="Env preset name (default: auto from slug)")
        parser.add_argument("--project-id", default="", help="Railway project UUID (saved to vault)")
        parser.add_argument("--service-id", default="", help="Railway web service UUID (saved to vault)")
        parser.add_argument(
            "--paste-file",
            default="",
            help="Also write Raw Editor paste file (default: <repo>/.railway-variables-paste.env)",
        )
        parser.add_argument(
            "--postgres-service",
            default="Postgres",
            help="Postgres plugin name for DATABASE_URL reference (Postgres or PostgreSQL)",
        )

    def handle(self, *args, **options):
        slug = options["slug"].strip().lower()
        try:
            project = Project.objects.get(slug=slug)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Hub project '{slug}' not found") from exc

        if options["project_id"]:
            set_secret(project, "RAILWAY_PROJECT_ID", options["project_id"].strip())
            self.stdout.write(self.style.SUCCESS("Stored RAILWAY_PROJECT_ID in vault"))
        if options["service_id"]:
            set_secret(project, "RAILWAY_SERVICE_ID", options["service_id"].strip())
            self.stdout.write(self.style.SUCCESS("Stored RAILWAY_SERVICE_ID in vault"))

        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        if not token:
            raise CommandError("RAILWAY_API_TOKEN missing from vault")

        preset = options["preset"] or preset_for_project(project) or slug
        postgres_name = (
            options["postgres_service"].strip()
            if options["postgres_service"] != "Postgres"
            else (postgres_service_for_preset(preset) or "Postgres")
        )
        extra_vars = {"DATABASE_URL": "${{" + postgres_name + ".DATABASE_URL}}"}

        project_id = resolve_railway_project_id(project, token)
        if not project_id:
            self._write_paste_file(project, preset, extra_vars, options["paste_file"])
            raise CommandError(
                "Could not resolve Railway project ID. "
                "In Railway: Project → Settings → copy Project ID, then run:\n"
                f"  manage.py push_railway_env {slug} --project-id <uuid>\n"
                "Or paste .railway-variables-paste.env into Railway → web service → Variables."
            )

        service_id = resolve_railway_web_service_id(project, token, project_id)
        if not service_id:
            self._write_paste_file(project, preset, extra_vars, options["paste_file"])
            raise CommandError(
                f"Project ID {project_id} found but web service ID missing. "
                f"Railway → SilverFox web service → Settings → copy Service ID, then run:\n"
                f"  manage.py push_railway_env {slug} --service-id <uuid>"
            )

        try:
            result = auto_push_railway_env(
                project,
                preset=preset,
                project_id=project_id,
                service_id=service_id,
                variables=extra_vars,
            )
        except Exception as exc:
            self._write_paste_file(project, preset, extra_vars, options["paste_file"])
            raise CommandError(str(exc)) from exc

        remember_railway_targets(project, project_id, service_id)
        self.stdout.write(self.style.SUCCESS(result.get("message", "Pushed")))
        self.stdout.write(f"  project: {project_id}")
        self.stdout.write(f"  service: {service_id}")
        self.stdout.write(f"  keys: {', '.join(result.get('pushed') or [])}")

    def _write_paste_file(
        self,
        project: Project,
        preset: str,
        extra_vars: dict[str, str],
        paste_file: str,
    ) -> Path:
        vars_map = build_env_var_payload(project, preset=preset, variables=extra_vars)
        root = Path(project.local_path).resolve() if project.local_path else Path.cwd()
        path = Path(paste_file) if paste_file else root / ".railway-variables-paste.env"
        lines = [
            "# Paste into Railway → WEB service (not Postgres) → Variables → Raw Editor",
            "# Delete this file after paste — contains secrets",
            "",
        ]
        for key in sorted(vars_map.keys()):
            lines.append(f"{key}={vars_map[key]}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.stdout.write(self.style.WARNING(f"Wrote fallback paste file: {path}"))
        return path
