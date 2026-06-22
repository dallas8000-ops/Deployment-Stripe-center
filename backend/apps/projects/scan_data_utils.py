"""Atomic, nested-safe updates to Project.scan_data."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.projects.models import Project


def merge_scan_patch(scan: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge patch into scan_data (nested dicts are merged, not replaced)."""
    result = dict(scan)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            nested = dict(result[key])
            nested.update(value)
            result[key] = nested
        else:
            result[key] = value
    return result


def update_project_scan_data(project: Project, patch: dict[str, Any]) -> dict[str, Any]:
    """Apply patch to scan_data under row lock to avoid concurrent overwrites."""
    with transaction.atomic():
        locked = Project.objects.select_for_update().get(pk=project.pk)
        scan = merge_scan_patch(dict(locked.scan_data or {}), patch)
        locked.scan_data = scan
        locked.save(update_fields=["scan_data", "updated_at"])
    project.scan_data = scan
    return scan
