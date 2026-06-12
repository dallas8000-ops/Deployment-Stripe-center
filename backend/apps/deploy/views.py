from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin
from apps.runs.tasks import execute_pipeline
from apps.runs.serializers import PipelineRunSerializer
from apps.stripe_engine.readiness import readiness_label, run_readiness_checks, score_readiness
from django.shortcuts import get_object_or_404

from .infra import generate_and_write_infra, generate_infra_files, infra_summary
from .postgres import apply_postgres_schema, get_production_url, postgres_status, schema_sql, test_postgres_connection
from .provision import provision_postgres

_ERR_NO_LOCAL_PATH = "Set project local_path first."


class PostgresStatusView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        data = postgres_status(project, test_connection=True)
        data["manifest"] = (project.scan_data or {}).get("postgres")
        return Response(data)


class PostgresSchemaView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        self.get_project(project_slug)
        return Response({"schema": schema_sql()})


class PostgresProvisionView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        provider = request.data.get("provider", "neon")
        region = request.data.get("region")
        reuse = request.data.get("reuse", True)
        apply_schema = request.data.get("apply_schema", True)
        try:
            result = provision_postgres(
                project,
                provider=provider,
                region=region,
                reuse=bool(reuse),
                apply_schema=bool(apply_schema),
            )
        except (RuntimeError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class PostgresTestView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        from .postgres import get_database_url

        url = get_database_url(project)
        if not url:
            return Response({"ok": False, "message": "DATABASE_URL not in vault"}, status=status.HTTP_400_BAD_REQUEST)
        result = test_postgres_connection(url)
        status_code = status.HTTP_200_OK if result["ok"] else status.HTTP_400_BAD_REQUEST
        return Response(result, status=status_code)


class PostgresApplySchemaView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        result = apply_postgres_schema(project)
        status_code = status.HTTP_200_OK if result["ok"] else status.HTTP_400_BAD_REQUEST
        return Response(result, status=status_code)


class DeployReadinessView(ProjectOwnedMixin, APIView):
    """Deploy gate — readiness score + label before production."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        from pathlib import Path

        if not project.local_path:
            return Response({"error": _ERR_NO_LOCAL_PATH}, status=status.HTTP_400_BAD_REQUEST)
        root = Path(project.local_path).resolve()
        if not root.is_dir():
            return Response({"error": f"Project path not found: {root}"}, status=status.HTTP_400_BAD_REQUEST)
        app_url = request.query_params.get("app_url") or get_production_url(
            project, request.build_absolute_uri("/").rstrip("/")
        )
        checks = run_readiness_checks(project, root, production_url=app_url)
        score = score_readiness(checks)
        return Response(
            {
                "score": score,
                "label": readiness_label(score),
                "checks": [c.to_dict() for c in checks],
                "postgres": postgres_status(project),
            }
        )


class DeployRunView(ProjectOwnedMixin, APIView):
    """One-click deploy prep — full pipeline + readiness in one run."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        if not project.local_path:
            return Response({"error": _ERR_NO_LOCAL_PATH}, status=status.HTTP_400_BAD_REQUEST)

        options = {
            "mode": "deploy",
            "provision": request.data.get("provision", True),
            "generate": request.data.get("generate", True),
            "sync_env": request.data.get("sync_env", False),
            "force": request.data.get("force", False),
            "include_infra": request.data.get("include_infra", True),
            "provision_postgres": request.data.get("provision_postgres", True),
            "include_readiness": True,
            "push": request.data.get("push", False),
            "postgres_provider": request.data.get("postgres_provider", "neon"),
            "app_url": request.data.get("app_url")
            or get_production_url(project, request.build_absolute_uri("/").rstrip("/")),
        }
        run = PipelineRun.objects.create(
            project=project,
            started_by=request.user,
            options=options,
        )
        execute_pipeline.delay(str(run.id))
        return Response(PipelineRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class DeployPushView(ProjectOwnedMixin, APIView):
    """Run platform CLI deploy (vercel --prod, railway up, etc.)."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        from pathlib import Path

        from .platform import detect_deploy_platform
        from .platform_push import push_to_platform

        project = self.get_project(project_slug)
        if not project.local_path:
            return Response({"error": _ERR_NO_LOCAL_PATH}, status=status.HTTP_400_BAD_REQUEST)
        root = Path(project.local_path).resolve()
        if not root.is_dir():
            return Response({"error": f"Project path not found: {root}"}, status=status.HTTP_400_BAD_REQUEST)

        scan = project.scan_data or {}
        platform = request.data.get("platform") or scan.get("deployPlatform") or detect_deploy_platform(
            root, project.framework
        )
        result = push_to_platform(root, platform)
        status_code = status.HTTP_200_OK if result["success"] else status.HTTP_400_BAD_REQUEST
        return Response(result, status=status_code)


class DeployConfigView(ProjectOwnedMixin, APIView):
    """Read/write deploy.config.json in the client project repo."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        from pathlib import Path

        from .config import config_from_project, deploy_config_path

        project = self.get_project(project_slug)
        if not project.local_path:
            return Response({"error": _ERR_NO_LOCAL_PATH}, status=status.HTTP_400_BAD_REQUEST)
        root = Path(project.local_path).resolve()
        if not root.is_dir():
            return Response({"error": f"Project path not found: {root}"}, status=status.HTTP_400_BAD_REQUEST)

        path = deploy_config_path(root)
        return Response(
            {
                "config": config_from_project(project, root),
                "exists": path.is_file(),
                "path": str(path.relative_to(root)),
            }
        )

    def put(self, request, project_slug: str):
        from pathlib import Path

        from .config import normalize_deploy_config, sync_project_from_config, write_deploy_config

        project = self.get_project(project_slug)
        if not project.local_path:
            return Response({"error": _ERR_NO_LOCAL_PATH}, status=status.HTTP_400_BAD_REQUEST)
        root = Path(project.local_path).resolve()
        if not root.is_dir():
            return Response({"error": f"Project path not found: {root}"}, status=status.HTTP_400_BAD_REQUEST)

        body = request.data.get("config", request.data)
        if not isinstance(body, dict):
            return Response({"error": "config object required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            normalized = normalize_deploy_config(body)
            write_deploy_config(root, normalized)
            sync_project_from_config(project, normalized)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"config": normalized, "exists": True, "path": "deploy.config.json"})


class EnvPushView(ProjectOwnedMixin, APIView):
    """Push vault secrets directly to a Render or Railway service's environment variables."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        from .env_push import push_vault_env_to_platform

        project = self.get_project(project_slug)
        platform = request.data.get("platform")
        service_id = request.data.get("service_id") or request.data.get("serviceId", "")
        project_id = request.data.get("project_id") or request.data.get("projectId")
        environment_id = request.data.get("environment_id") or request.data.get("environmentId")
        keys = request.data.get("keys")

        if not platform:
            return Response(
                {"error": "platform is required (render or railway)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not service_id:
            return Response(
                {"error": "service_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = push_vault_env_to_platform(
                project,
                platform,
                service_id,
                project_id=project_id,
                environment_id=environment_id,
                keys=keys if isinstance(keys, list) else None,
            )
        except (RuntimeError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)


class InfraPreviewView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        from pathlib import Path

        if not project.local_path:
            return Response({"error": _ERR_NO_LOCAL_PATH}, status=status.HTTP_400_BAD_REQUEST)
        root = Path(project.local_path).resolve()
        prod_url = request.query_params.get("app_url") or get_production_url(
            project, request.build_absolute_uri("/").rstrip("/")
        )
        files = generate_infra_files(project, root, prod_url=prod_url)
        return Response(infra_summary(files))


class InfraGenerateView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        force = bool(request.data.get("force", False))
        prod_url = request.data.get("app_url") or get_production_url(
            project, request.build_absolute_uri("/").rstrip("/")
        )
        try:
            files, results = generate_and_write_infra(project, force=force, prod_url=prod_url)
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                **infra_summary(files),
                "written": [
                    {"path": r.path, "action": r.action}
                    for r in results
                    if r.action != "skipped"
                ],
                "skipped": [r.path for r in results if r.action == "skipped"],
            },
            status=status.HTTP_201_CREATED,
        )
