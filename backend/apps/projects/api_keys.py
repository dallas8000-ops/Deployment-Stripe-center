"""Project API keys for CI and automation."""

from __future__ import annotations

import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.projects.models import Project


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, hash)."""
    raw = secrets.token_urlsafe(32)
    full = f"si_{raw}"
    prefix = full[:12]
    digest = hashlib.sha256(full.encode()).hexdigest()
    return full, prefix, digest


class ProjectApiKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=120)
    key_prefix = models.CharField(max_length=16)
    key_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_api_keys",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.project.slug}:{self.name}"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @classmethod
    def create_for_project(cls, project: Project, name: str, user) -> tuple["ProjectApiKey", str]:
        full, prefix, digest = generate_api_key()
        row = cls.objects.create(
            project=project,
            name=name,
            key_prefix=prefix,
            key_hash=digest,
            created_by=user,
        )
        return row, full

    @classmethod
    def authenticate(cls, raw_key: str) -> Project | None:
        if not raw_key.startswith("si_"):
            return None
        digest = hashlib.sha256(raw_key.encode()).hexdigest()
        row = cls.objects.filter(key_hash=digest, revoked_at__isnull=True).select_related("project").first()
        if not row:
            return None
        row.last_used_at = timezone.now()
        row.save(update_fields=["last_used_at"])
        return row.project
