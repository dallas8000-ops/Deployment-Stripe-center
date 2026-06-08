from __future__ import annotations

from celery import shared_task

from apps.projects.models import Project
from apps.stripe_engine.drift import detect_drift, persist_drift_snapshot
from apps.vault.models import VaultSecret


@shared_task(name="stripe_engine.check_project_drift")
def check_project_drift(project_id: str) -> dict:
    project = Project.objects.get(id=project_id)
    try:
        result = detect_drift(project)
    except RuntimeError as exc:
        return {"project": project.slug, "skipped": True, "reason": str(exc)}

    persist_drift_snapshot(project, result)
    return {"project": project.slug, "driftCount": result["driftCount"]}


@shared_task(name="stripe_engine.check_all_projects_drift")
def check_all_projects_drift() -> dict:
    project_ids = (
        VaultSecret.objects.filter(key_name="STRIPE_SECRET_KEY")
        .values_list("project_id", flat=True)
        .distinct()
    )
    checked = 0
    drifted = 0
    for pid in project_ids:
        result = check_project_drift(str(pid))
        if not result.get("skipped"):
            checked += 1
            if result.get("driftCount", 0) > 0:
                drifted += 1
    return {"checked": checked, "drifted": drifted}
