from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.projects.git_clone import pull_project_repo
from apps.projects.github_pr import create_setup_pull_request
from apps.core.access import ROLE_RANK, org_membership, projects_for_user
from apps.stripe_core.portfolio_catalog import DASHBOARD_HIDDEN_PROJECT_SLUGS
from apps.organizations.models import Organization
from apps.projects.api_keys import ProjectApiKey
from apps.projects.tasks import pull_repo_task
from .scanner import ProjectScanner
from .serializers import ProjectScanSerializer, ProjectSerializer, ProjectUpdateSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "slug"

    def get_queryset(self):
        base = projects_for_user(self.request.user).distinct()
        if self.action == "list":
            return base.exclude(slug__in=DASHBOARD_HIDDEN_PROJECT_SLUGS)
        return base

    def list(self, request, *args, **kwargs):
        from apps.stripe_core.portfolio_workspace import reconcile_hub_workspace

        queryset = self.filter_queryset(self.get_queryset())
        for project in queryset:
            reconcile_hub_workspace(project)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        from apps.core.access import get_project_for_user
        from apps.stripe_core.portfolio_catalog import canonical_project_slug, is_merged_legacy_slug
        from apps.stripe_core.portfolio_workspace import (
            reconcile_hub_workspace,
            sync_portfolio_scan_metadata,
        )

        slug = kwargs[self.lookup_field]
        if is_merged_legacy_slug(slug):
            target = canonical_project_slug(slug)
            return Response(
                {
                    "merged": True,
                    "mergedInto": target,
                    "redirect": f"/projects/{target}",
                    "message": f"Project '{slug}' was merged into '{target}'.",
                },
                status=status.HTTP_301_MOVED_PERMANENTLY,
                headers={"Location": f"/projects/{target}"},
            )

        project = get_project_for_user(request.user, slug)
        reconcile_hub_workspace(project)
        sync_portfolio_scan_metadata(project)
        serializer = self.get_serializer(project)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return ProjectUpdateSerializer
        return ProjectSerializer

    @action(detail=True, methods=["post"])
    def scan(self, request, slug=None):
        from apps.core.access import get_project_for_user
        from apps.stripe_core.portfolio_workspace import (
            reconcile_hub_workspace,
            should_repair_local_path,
        )

        project = get_project_for_user(request.user, slug)
        body = ProjectScanSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        scan_path = body.validated_data.get("local_path") or project.local_path
        if scan_path and should_repair_local_path(project, scan_path):
            scan_path, _ = reconcile_hub_workspace(project)
        elif not scan_path:
            scan_path, _ = reconcile_hub_workspace(project)

        from apps.stripe_core.portfolio_workspace import workspace_path_error

        path_err = workspace_path_error(project, scan_path)
        if path_err:
            return Response({"error": path_err}, status=status.HTTP_400_BAD_REQUEST)

        if not scan_path:
            return Response(
                {"error": "Set local_path on the project or pass local_path in the request body."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if body.validated_data.get("local_path"):
            project.local_path = scan_path
            project.save(update_fields=["local_path", "updated_at"])

        try:
            from pathlib import Path

            from apps.deploy.platform import detect_deploy_platform
            from apps.stripe_core.portfolio_catalog import catalog_by_slug
            from apps.stripe_core.portfolio_workspace import relative_scan_root, resolve_scan_root

            repo_root = Path(scan_path).resolve()
            scan_root = resolve_scan_root(repo_root)
            result = (
                ProjectScanner(repo_root).scan_monorepo()
                if scan_root == repo_root
                else ProjectScanner(scan_root).scan()
            )
        except FileNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        data = result.to_dict()
        if data.get("next_router"):
            data["nextRouter"] = data["next_router"]
        catalog = catalog_by_slug(project.slug or "")
        production_url = str(
            (catalog or {}).get("productionUrl")
            or (project.scan_data or {}).get("productionUrl")
            or ""
        )
        backend_rel = relative_scan_root(repo_root, scan_root)
        if backend_rel:
            data["scanBackendPath"] = backend_rel
        data["deployPlatform"] = detect_deploy_platform(
            scan_root,
            data.get("framework", "unknown"),
            production_url=production_url,
        )
        if catalog:
            if catalog.get("productionUrl"):
                url = str(catalog["productionUrl"]).rstrip("/")
                data["productionUrl"] = url
                data["production_url"] = url
            if catalog.get("webhookPath"):
                data["webhookPath"] = catalog["webhookPath"]
        project.framework = data["framework"]
        project.language = data["language"]
        project.scan_data = data
        project.last_scanned_at = timezone.now()
        project.save(
            update_fields=["framework", "language", "scan_data", "last_scanned_at", "updated_at"]
        )

        return Response(ProjectSerializer(project).data)

    @action(detail=True, methods=["post"], url_path="git-pull")
    def git_pull(self, request, slug=None):
        project = self.get_object()
        if not project.git_url:
            return Response(
                {"error": "Set git_url on the project first (Settings)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        async_mode = bool(request.data.get("async", False))

        if async_mode:
            task = pull_repo_task.delay(str(project.id))
            return Response(
                {"status": "queued", "task_id": task.id, "project": ProjectSerializer(project).data},
                status=status.HTTP_202_ACCEPTED,
            )

        try:
            result = pull_project_repo(project)
        except (RuntimeError, ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({**result, "project": ProjectSerializer(project).data})

    @action(detail=True, methods=["post"], url_path="clone")
    def clone(self, request, slug=None):
        """Deprecated — use git-pull. Never clones into this hub repo."""
        return Response(
            {
                "error": (
                    "Clone into this hub was removed. Set local_path to your real app folder "
                    "and use POST .../git-pull/ to run git pull there."
                )
            },
            status=status.HTTP_410_GONE,
        )

    @action(detail=True, methods=["post"], url_path="open-pr")
    def open_pr(self, request, slug=None):
        project = self.get_object()
        if not project.local_path:
            return Response({"error": "Set project local_path first."}, status=status.HTTP_400_BAD_REQUEST)
        require_ci = bool(request.data.get("require_ci_passing", False))
        if require_ci and project.git_url:
            try:
                from apps.projects.github_ci import get_github_ci_status

                ci = get_github_ci_status(project)
                if not ci.get("success"):
                    return Response(
                        {"error": f"GitHub CI not passing on {ci.get('ref')} (state: {ci.get('state')})"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except (RuntimeError, ValueError) as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = create_setup_pull_request(
                project,
                commit_message=request.data.get("commit_message", "chore: Stripe Installer setup"),
                pr_title=request.data.get("title"),
                pr_body=request.data.get("body"),
            )
        except (RuntimeError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def audit(self, request, slug=None):
        project = self.get_object()
        rows = []
        for log in project.audit_logs.select_related("actor").all()[:50]:
            rows.append(
                {
                    "id": log.id,
                    "action": log.action,
                    "detail": log.detail,
                    "created_at": log.created_at.isoformat(),
                    "actor": log.actor.email if log.actor else None,
                }
            )
        return Response({"entries": rows})

    @action(detail=True, methods=["get", "post"], url_path="api-keys")
    def api_keys(self, request, slug=None):
        from apps.core.access import get_project_for_user

        project = get_project_for_user(request.user, slug, min_role="admin")

        if request.method == "GET":
            rows = []
            for key in project.api_keys.filter(revoked_at__isnull=True):
                rows.append(
                    {
                        "id": str(key.id),
                        "name": key.name,
                        "prefix": key.key_prefix,
                        "created_at": key.created_at.isoformat(),
                        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
                    }
                )
            return Response({"keys": rows})

        name = (request.data or {}).get("name") or "CI key"
        row, full_key = ProjectApiKey.create_for_project(project, name, request.user)
        from apps.projects.audit import log_audit

        log_audit(project, "api_key.created", actor=request.user, detail={"name": name, "prefix": row.key_prefix})
        return Response(
            {
                "id": str(row.id),
                "name": row.name,
                "prefix": row.key_prefix,
                "key": full_key,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], url_path=r"api-keys/(?P<key_id>[^/.]+)")
    def revoke_api_key(self, request, slug=None, key_id=None):
        from apps.core.access import get_project_for_user
        from django.utils import timezone

        project = get_project_for_user(request.user, slug, min_role="admin")
        key = project.api_keys.filter(id=key_id, revoked_at__isnull=True).first()
        if not key:
            return Response({"error": "API key not found"}, status=404)
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        from apps.projects.audit import log_audit

        log_audit(project, "api_key.revoked", actor=request.user, detail={"prefix": key.key_prefix})
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="git-pull-status")
    def git_pull_status(self, request, slug=None):
        return Response({"status": "idle", "local_path": self.get_object().local_path})
