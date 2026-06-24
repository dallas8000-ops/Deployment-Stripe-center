"""Audit and rename Railway services for portfolio monorepos (stay in one project)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.deploy.railway_client import railway_gql
from apps.deploy.railway_layout import audit_report, layout_for_slug
from apps.deploy.railway_resolve import _list_railway_projects_with_domains
from apps.projects.models import Project
from apps.stripe_core.hub_keys import get_hub_project, repair_project_vault_from_hub
from apps.vault.models import get_secret


class Command(BaseCommand):
    help = "Rename Elite Fintech Railway services to a consistent prefix (same project, one app)"

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="elite-fintech-systems", help="Hub project slug")
        parser.add_argument("--user", default="", help="Owner email")
        parser.add_argument("--rename", action="store_true", help="Rename services to canonical names")
        parser.add_argument(
            "--delete-empty-project",
            metavar="NAME",
            default="",
            help="Delete an accidentally created empty Railway project by name",
        )

    def handle(self, *args, **options):
        slug = (options.get("slug") or "").strip().lower()
        layout = layout_for_slug(slug)
        if not layout:
            raise CommandError(f"No Railway layout defined for slug '{slug}'")

        User = get_user_model()
        email = (options.get("user") or "").strip()
        owner = User.objects.get(email=email) if email else User.objects.first()
        if not owner:
            raise CommandError("No users found")

        project = Project.objects.filter(owner=owner, slug=slug).first()
        if not project:
            raise CommandError(f"Hub project '{slug}' not found for {owner.email}")

        hub = get_hub_project(owner)
        if hub:
            repair_project_vault_from_hub(project, hub)
        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        if not token:
            raise CommandError("RAILWAY_API_TOKEN not in vault — add at railway.com/account/tokens")

        projects = _list_railway_projects_with_domains(token)

        delete_name = (options.get("delete_empty_project") or "").strip()
        if delete_name:
            self._delete_empty_project(token, projects, delete_name)
            projects = _list_railway_projects_with_domains(token)

        report = audit_report(layout, projects)

        self.stdout.write(self.style.MIGRATE_HEADING(f"Railway app: {layout['app_label']}"))
        self.stdout.write("One app = api + web + db services in your existing Railway project.")
        self.stdout.write("")

        if report["split_across_projects"]:
            self.stdout.write(
                self.style.WARNING(
                    "Elite Fintech services span multiple Railway projects — keep them in one project only."
                )
            )

        for hit in report["project_hits"]:
            self.stdout.write(
                f"  Project: {hit['name']} — {hit['elite_hits']} service(s) for this app, "
                f"{hit['service_count']} total in project"
            )

        self.stdout.write("")
        for info in report["matched"].values():
            rename = " -> RENAME" if info["needs_rename"] else ""
            domains = ", ".join(info["domains"][:2]) or "(no public domain)"
            self.stdout.write(
                f"  [{info['role']}] {info['current_name']} @ {info['project_name']}{rename}"
            )
            self.stdout.write(f"         domains: {domains}")

        for missing in report["missing"]:
            self.stdout.write(self.style.WARNING(f"  [missing] {missing}"))

        if options.get("rename"):
            renamed = 0
            for info in report["matched"].values():
                if not info["needs_rename"]:
                    continue
                self._rename_service(token, info["service_id"], info["target_name"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Renamed {info['current_name']} -> {info['target_name']}"
                    )
                )
                renamed += 1
            if renamed == 0:
                self.stdout.write("All matched services already use canonical names.")

    def _delete_empty_project(self, token: str, projects: list[dict], name: str) -> None:
        target = name.strip().lower()
        for proj in projects:
            if (proj.get("name") or "").strip().lower() != target:
                continue
            if proj.get("services"):
                raise CommandError(
                    f"Project '{proj['name']}' still has services — delete manually if empty"
                )
            railway_gql(
                token,
                "mutation($id: String!) { projectDelete(id: $id) }",
                {"id": proj["id"]},
            )
            self.stdout.write(self.style.SUCCESS(f"Deleted empty project: {proj['name']}"))
            return
        self.stdout.write(self.style.WARNING(f"No empty project named '{name}' found"))

    def _rename_service(self, token: str, service_id: str, name: str) -> None:
        railway_gql(
            token,
            """
            mutation($id: String!, $input: ServiceUpdateInput!) {
              serviceUpdate(id: $id, input: $input) { id name }
            }
            """,
            {"id": service_id, "input": {"name": name}},
        )
