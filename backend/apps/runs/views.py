from pathlib import Path

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin
from apps.projects.models import Project
from apps.runs.artifacts import resolve_run_files
from apps.runs.models import PipelineRun
from apps.runs.serializers import PipelineRunSerializer, StartPipelineSerializer
from apps.runs.tasks import execute_pipeline
from apps.stripe_engine.codegen import build_zip, generate_all
from apps.stripe_engine.diagnostics import run_diagnostics
from apps.stripe_engine.provision import load_manifest
from apps.stripe_engine.readiness import readiness_label, run_readiness_checks, score_readiness
from apps.stripe_engine.repair import run_auto_fix, run_repair_action
from apps.stripe_engine.verify import verify_stripe_keys
from apps.vault.models import get_secret


class VerifyKeysView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        secret = get_secret(project, "STRIPE_SECRET_KEY")
        publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
        result = verify_stripe_keys(secret, publishable)
        return Response(result.to_public_dict())


class PipelineRunListCreateView(ProjectOwnedMixin, generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = PipelineRunSerializer

    def get_queryset(self):
        project = self.get_project(self.kwargs["project_slug"])
        return PipelineRun.objects.filter(project=project).prefetch_related("logs")

    def create(self, request, *args, **kwargs):
        project = self.get_project(kwargs["project_slug"])
        body = StartPipelineSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        if not project.local_path:
            return Response(
                {"error": "Set project local_path before running the pipeline."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        options = dict(body.validated_data)
        if not options.get("app_url"):
            options["app_url"] = request.build_absolute_uri("/").rstrip("/")

        run = PipelineRun.objects.create(
            project=project,
            started_by=request.user,
            options=options,
        )
        execute_pipeline.delay(str(run.id))

        return Response(
            PipelineRunSerializer(run).data,
            status=status.HTTP_202_ACCEPTED,
        )


class PipelineRunDetailView(ProjectOwnedMixin, generics.RetrieveAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = PipelineRunSerializer
    lookup_field = "id"
    lookup_url_kwarg = "run_id"

    def get_queryset(self):
        project = self.get_project(self.kwargs["project_slug"])
        return PipelineRun.objects.filter(project=project).prefetch_related("logs")


class PipelineRunDownloadView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str, run_id: str):
        project = self.get_project(project_slug)
        run = get_object_or_404(PipelineRun, id=run_id, project=project)
        files = resolve_run_files(run)
        if not files:
            return Response(
                {"error": "No generated files available for this run."},
                status=status.HTTP_404_NOT_FOUND,
            )
        zip_bytes = build_zip(files, prefix=f"{project.slug}-stripe/")
        response = HttpResponse(zip_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{project.slug}-stripe-{run.id}.zip"'
        return response


class CodegenDownloadView(ProjectOwnedMixin, APIView):
    """Generate code from manifest and return a zip (no Stripe API calls)."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        from pathlib import Path

        project = self.get_project(project_slug)
        if not project.local_path:
            return Response(
                {"error": "Set project local_path before downloading generated code."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        root = Path(project.local_path).resolve()
        manifest = load_manifest(root)
        app_url = request.data.get("app_url") or request.build_absolute_uri("/").rstrip("/")
        files = generate_all(
            project.framework,
            manifest,
            app_url=app_url,
            next_router=(project.scan_data or {}).get("nextRouter"),
        )
        if not files:
            return Response({"error": "No files to generate."}, status=status.HTTP_404_NOT_FOUND)

        zip_bytes = build_zip(files, prefix=f"{project.slug}-stripe/")
        response = HttpResponse(zip_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{project.slug}-stripe-codegen.zip"'
        return response


def _require_local_path(project: Project) -> Path:
    from pathlib import Path

    if not project.local_path:
        raise ValueError("Set project local_path first.")
    root = Path(project.local_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project path not found: {root}")
    return root


class DiagnoseView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            root = _require_local_path(project)
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        report = run_diagnostics(project, root)
        scan_data = dict(project.scan_data or {})
        scan_data["lastHealthScore"] = report.health_score
        scan_data["lastDiagnosedAt"] = report.scanned_at
        project.scan_data = scan_data
        project.save(update_fields=["scan_data", "updated_at"])
        return Response(report.to_dict())


class ReadinessView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            root = _require_local_path(project)
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        app_url = request.query_params.get("app_url") or request.build_absolute_uri("/").rstrip("/")
        checks = run_readiness_checks(project, root, production_url=app_url)
        score = score_readiness(checks)
        scan_data = dict(project.scan_data or {})
        scan_data["lastReadinessScore"] = score
        scan_data["lastReadinessLabel"] = readiness_label(score)
        project.scan_data = scan_data
        project.save(update_fields=["scan_data", "updated_at"])
        return Response(
            {
                "score": score,
                "label": readiness_label(score),
                "checks": [c.to_dict() for c in checks],
            }
        )


class FixView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        try:
            _require_local_path(project)
        except (ValueError, FileNotFoundError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data or {}
        action = data.get("action")
        issue_ids = data.get("issue_ids") or data.get("issueIds")
        force = bool(data.get("force"))
        app_url = data.get("app_url") or request.build_absolute_uri("/").rstrip("/")

        if action:
            try:
                repair = run_repair_action(project, action, force=force, app_url=app_url)
                from pathlib import Path

                report = run_diagnostics(project, Path(project.local_path).resolve())
                return Response(
                    {
                        "repairs": [repair.to_dict()],
                        "report": report.to_dict(),
                    }
                )
            except Exception as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if data.get("all"):
            repairs, report = run_auto_fix(project, force=force, app_url=app_url)
        else:
            repairs, report = run_auto_fix(
                project,
                issue_ids=issue_ids,
                force=force,
                app_url=app_url,
            )

        return Response(
            {
                "repairs": [r.to_dict() for r in repairs],
                "report": report.to_dict(),
            }
        )


class StripeConfigView(ProjectOwnedMixin, APIView):
    """Read/write stripe.config.json in the client project repo."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        from apps.stripe_engine.stripe_config import config_from_disk, stripe_config_path

        project = self.get_project(project_slug)
        if not project.local_path:
            return Response({"error": "Set project local_path first."}, status=status.HTTP_400_BAD_REQUEST)
        root = Path(project.local_path).resolve()
        if not root.is_dir():
            return Response({"error": f"Project path not found: {root}"}, status=status.HTTP_400_BAD_REQUEST)

        path = stripe_config_path(root)
        return Response(
            {
                "config": config_from_disk(root),
                "exists": path.is_file(),
                "path": "stripe.config.json",
            }
        )

    def put(self, request, project_slug: str):
        from apps.stripe_engine.stripe_config import normalize_stripe_config, write_stripe_config

        project = self.get_project(project_slug)
        if not project.local_path:
            return Response({"error": "Set project local_path first."}, status=status.HTTP_400_BAD_REQUEST)
        root = Path(project.local_path).resolve()
        if not root.is_dir():
            return Response({"error": f"Project path not found: {root}"}, status=status.HTTP_400_BAD_REQUEST)

        body = request.data.get("config", request.data)
        if not isinstance(body, dict):
            return Response({"error": "config object required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            normalized = normalize_stripe_config(body)
            write_stripe_config(root, normalized)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"config": normalized, "exists": True, "path": "stripe.config.json"})
