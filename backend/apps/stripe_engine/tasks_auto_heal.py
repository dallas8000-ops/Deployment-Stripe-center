"""Celery tasks for automated self-healing."""

from __future__ import annotations

from celery import shared_task

from apps.projects.models import Project
from apps.stripe_engine.auto_heal import HealPolicy, run_auto_heal_with_drift


@shared_task(name="stripe_engine.auto_heal_project")
def auto_heal_project_task(project_id: str, app_url: str = "http://localhost:8000") -> dict:
    """Run auto-healing on a specific project."""
    try:
        project = Project.objects.get(id=project_id)
        result = run_auto_heal_with_drift(project, policy=HealPolicy(), app_url=app_url)
        return {
            "project": project.slug,
            "success": result.success,
            "issuesDetected": result.issues_detected,
            "issuesAutoFixed": result.issues_auto_fixed,
            "issuesSkipped": result.issues_skipped,
            "timestamp": result.timestamp,
        }
    except Project.DoesNotExist:
        return {"project": project_id, "skipped": True, "reason": "Project not found"}
    except Exception as exc:
        return {"project": project_id, "skipped": True, "reason": str(exc)}


@shared_task(name="stripe_engine.auto_heal_all_projects")
def auto_heal_all_projects_task(app_url: str = "http://localhost:8000") -> dict:
    """Run auto-healing on all projects with drift detected."""
    from apps.vault.models import VaultSecret

    project_ids = (
        VaultSecret.objects.filter(key_name="STRIPE_SECRET_KEY")
        .values_list("project_id", flat=True)
        .distinct()
    )

    healed = 0
    skipped = 0
    for pid in project_ids:
        result = auto_heal_project_task(str(pid), app_url)
        if result.get("skipped"):
            skipped += 1
        elif result.get("success"):
            healed += 1

    return {"healed": healed, "skipped": skipped, "total": len(project_ids)}
