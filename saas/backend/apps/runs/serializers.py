from rest_framework import serializers

from apps.runs.models import PipelineRun, PipelineRunLog


class PipelineRunLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineRunLog
        fields = ("step", "status", "message", "detail", "score", "created_at")


class PipelineRunSerializer(serializers.ModelSerializer):
    logs = PipelineRunLogSerializer(many=True, read_only=True)

    class Meta:
        model = PipelineRun
        fields = (
            "id",
            "status",
            "options",
            "result",
            "error_message",
            "readiness_score",
            "created_at",
            "started_at",
            "completed_at",
            "logs",
        )
        read_only_fields = fields


class StartPipelineSerializer(serializers.Serializer):
    provision = serializers.BooleanField(default=True)
    generate = serializers.BooleanField(default=True)
    sync_env = serializers.BooleanField(default=False)
    force = serializers.BooleanField(default=False)
    include_readiness = serializers.BooleanField(default=True)
    app_url = serializers.URLField(required=False, allow_blank=True)
