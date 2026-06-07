from rest_framework import serializers

from apps.runs.models import PipelineRun

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    latest_readiness_score = serializers.SerializerMethodField()
    last_run_status = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "git_url",
            "local_path",
            "framework",
            "language",
            "scan_data",
            "last_scanned_at",
            "created_at",
            "updated_at",
            "latest_readiness_score",
            "last_run_status",
        )
        read_only_fields = (
            "id",
            "slug",
            "framework",
            "language",
            "scan_data",
            "last_scanned_at",
            "created_at",
            "updated_at",
            "latest_readiness_score",
            "last_run_status",
        )

    def get_latest_readiness_score(self, obj: Project) -> int | None:
        run = (
            PipelineRun.objects.filter(project=obj, status=PipelineRun.Status.COMPLETED)
            .order_by("-completed_at")
            .first()
        )
        if run and run.readiness_score is not None:
            return run.readiness_score
        scan = obj.scan_data or {}
        return scan.get("lastReadinessScore")

    def get_last_run_status(self, obj: Project) -> str | None:
        run = PipelineRun.objects.filter(project=obj).order_by("-created_at").first()
        return run.status if run else None


class ProjectScanSerializer(serializers.Serializer):
    local_path = serializers.CharField(required=False, allow_blank=True, max_length=500)
