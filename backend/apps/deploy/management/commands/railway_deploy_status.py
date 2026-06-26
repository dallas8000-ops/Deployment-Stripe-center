"""Show Railway deployment status and optionally trigger a redeploy."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.env_push import _railway_environment_id, _railway_gql
from apps.deploy.railway_resolve import (
    _list_railway_services,
    _service_public_hosts,
    resolve_railway_project_id,
    resolve_railway_web_service_id,
)
from apps.projects.models import Project
from apps.vault.models import get_secret


class Command(BaseCommand):
    help = "List latest Railway deployments for a project and optionally trigger redeploy."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Hub project slug")
        parser.add_argument(
            "--deploy",
            action="store_true",
            help="Trigger serviceInstanceDeployV2 on the web service",
        )
        parser.add_argument("--limit", type=int, default=5, help="Deployments to list")

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

        env_id = _railway_environment_id(token, project_id)
        services = _list_railway_services(token, project_id)
        svc_name = next((s["name"] for s in services if s["id"] == service_id), service_id)
        hosts = _service_public_hosts(token, project_id, service_id)

        self.stdout.write(f"\n=== Railway deploy status: {slug} ===")
        self.stdout.write(f"Service: {svc_name} ({service_id})")
        self.stdout.write(f"Public hosts: {', '.join(sorted(hosts)) or '(none — generate domain in Networking)'}")

        data = _railway_gql(
            token,
            """
            query($input: DeploymentListInput!, $first: Int!) {
              deployments(input: $input, first: $first) {
                edges { node { id status createdAt updatedAt } }
              }
            }
            """,
            {
                "input": {
                    "projectId": project_id,
                    "serviceId": service_id,
                    "environmentId": env_id,
                },
                "first": max(1, options["limit"]),
            },
        )
        edges = ((data.get("deployments") or {}).get("edges") or [])
        if not edges:
            self.stdout.write(self.style.WARNING("\nNo deployments found for this service."))
        else:
            self.stdout.write("\nRecent deployments:")
            for edge in edges:
                node = edge.get("node") or {}
                status = node.get("status") or "?"
                dep_id = node.get("id") or "?"
                created = node.get("createdAt") or ""
                style = self.style.SUCCESS if str(status).upper() in ("SUCCESS", "ACTIVE") else self.style.WARNING
                if str(status).upper() in ("FAILED", "CRASHED"):
                    style = self.style.ERROR
                self.stdout.write(style(f"  {created}  {status}  {dep_id}"))

        if options["deploy"]:
            self.stdout.write("\nTriggering redeploy…")
            deploy_data = _railway_gql(
                token,
                """
                mutation($serviceId: String!, $environmentId: String!) {
                  serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
                }
                """,
                {"serviceId": service_id, "environmentId": env_id},
            )
            payload = deploy_data.get("serviceInstanceDeployV2") or {}
            if isinstance(payload, dict):
                dep_id = payload.get("id") or "?"
            else:
                dep_id = str(payload)
            self.stdout.write(self.style.SUCCESS(f"Deploy triggered: {dep_id}"))
            self.stdout.write(
                f"Dashboard: https://railway.app/project/{project_id}/service/{service_id}"
            )
