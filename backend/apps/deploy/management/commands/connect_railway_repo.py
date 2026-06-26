"""Connect a GitHub repo to a Railway service and trigger deploy."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.railway_deploy import (
    connect_railway_github,
    ensure_railway_github_and_deploy,
    github_repo_slug,
    trigger_railway_deploy,
)
from apps.deploy.railway_resolve import resolve_railway_project_id, resolve_railway_web_service_id
from apps.projects.models import Project
from apps.vault.models import get_secret


class Command(BaseCommand):
    help = "Connect GitHub repo to Railway web service and trigger deploy."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Hub project slug")
        parser.add_argument("--repo", default="", help="GitHub repo owner/name")
        parser.add_argument("--branch", default="main")
        parser.add_argument("--no-deploy", action="store_true")

    def handle(self, *args, **options):
        slug = options["slug"].strip().lower()
        try:
            project = Project.objects.get(slug=slug)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project '{slug}' not found") from exc

        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        if not token:
            raise CommandError("RAILWAY_API_TOKEN missing from vault")

        project_id = resolve_railway_project_id(project, token)
        service_id = resolve_railway_web_service_id(project, token, project_id)
        if not project_id or not service_id:
            raise CommandError("Could not resolve Railway project/service IDs")

        repo = (options["repo"] or "").strip() or github_repo_slug(project)
        if not repo:
            raise CommandError("Pass --repo owner/name or set project git_url in hub")

        branch = options["branch"].strip() or "main"
        if options["no_deploy"]:
            self.stdout.write(f"Connecting {repo}@{branch} to service {service_id}…")
            connect_railway_github(token, service_id, repo, branch=branch)
            self.stdout.write(self.style.SUCCESS("GitHub repo connected."))
            return

        result = ensure_railway_github_and_deploy(
            project,
            token,
            project_id,
            service_id,
            branch=branch,
        )
        self.stdout.write(self.style.SUCCESS(result.get("message", "Done")))
        if result.get("deploymentId"):
            self.stdout.write(f"Deploy: {result['deploymentId']}")
        self.stdout.write(
            f"https://railway.app/project/{project_id}/service/{service_id}"
        )
