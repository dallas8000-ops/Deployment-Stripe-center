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
from apps.stripe_installer.codegen import build_zip, generate_all
from apps.stripe_installer.provision import load_manifest
from apps.stripe_installer.stripe_advisor import run_stripe_advisor
from apps.stripe_installer.verify import verify_stripe_keys
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


class StripeAdvisorView(ProjectOwnedMixin, APIView):
    """Classify webhook failures and return step-by-step Dashboard/hosting playbooks."""

    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        root = None
        if project.local_path:
            candidate = Path(project.local_path).resolve()
            if candidate.is_dir():
                root = candidate
        report = run_stripe_advisor(project, root)
        scan_data = dict(project.scan_data or {})
        scan_data["lastAdvisorAt"] = report["scannedAt"]
        scan_data["lastAdvisorRootCause"] = report["primaryRootCause"]
        scan_data["webhookErrorRisk"] = report["webhookErrorRisk"]
        project.scan_data = scan_data
        project.save(update_fields=["scan_data", "updated_at"])
        return Response(report)


class StripeConfigView(ProjectOwnedMixin, APIView):
    """Read/write stripe.config.json in the client project repo."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        from apps.stripe_installer.stripe_config import config_from_disk, stripe_config_path

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
        from apps.stripe_installer.stripe_config import normalize_stripe_config, write_stripe_config

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
