from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model

from apps.projects.models import AuditLog, Project

User = get_user_model()


def log_audit(
    project: Project,
    action: str,
    *,
    actor: User | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    return AuditLog.objects.create(
        project=project,
        actor=actor,
        action=action,
        detail=detail or {},
    )
