from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class PipelineRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="pipeline_runs",
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pipeline_runs",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    options = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    readiness_score = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Run {self.id} ({self.status})"


class PipelineRunLog(models.Model):
    run = models.ForeignKey(PipelineRun, on_delete=models.CASCADE, related_name="logs")
    step = models.CharField(max_length=64)
    status = models.CharField(max_length=16)
    message = models.TextField()
    detail = models.BooleanField(default=False)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
