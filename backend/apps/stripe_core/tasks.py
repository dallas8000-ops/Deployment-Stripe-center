from __future__ import annotations

from celery import shared_task

from apps.core.distributed_lock import beat_singleton
from apps.projects.models import Project
from apps.stripe_core.auto_heal import HealPolicy, run_auto_heal_with_drift
from apps.diagnostics.drift import detect_drift, persist_drift_snapshot
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
@beat_singleton("check_all_projects_drift", ttl_seconds=7200)
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
@beat_singleton("auto_heal_all_projects", ttl_seconds=7200)
def auto_heal_all_projects_task(app_url: str = "http://localhost:8000") -> dict:
    """Run auto-healing on all projects with drift detected."""
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


@shared_task(name="stripe_engine.health_monitor_all_projects")
@beat_singleton("health_monitor_all_projects", ttl_seconds=3600)
def health_monitor_all_projects_task() -> dict:
    """Run health monitoring on all projects and alert on critical issues."""
    from apps.stripe_core.health_monitor import run_all_projects_health_monitor

    result = run_all_projects_health_monitor()
    summary = result.get("summary", {})

    # Log critical projects for alerting
    critical_projects = [
        r for r in result.get("reports", [])
        if r.get("overallStatus") == "critical"
    ]

    return {
        "total": summary.get("total", 0),
        "healthy": summary.get("healthy", 0),
        "warning": summary.get("warning", 0),
        "critical": summary.get("critical", 0),
        "criticalProjects": critical_projects,
        "timestamp": result.get("timestamp"),
    }


@shared_task(name="stripe_engine.anomaly_detection_all_projects")
@beat_singleton("anomaly_detection_all_projects", ttl_seconds=7200)
def anomaly_detection_all_projects_task() -> dict:
    """Run anomaly detection on all projects."""
    from apps.stripe_core.anomaly_detection import run_all_projects_anomaly_detection

    result = run_all_projects_anomaly_detection()
    summary = result.get("summary", {})

    return {
        "totalProjects": summary.get("totalProjects", 0),
        "totalAnomalies": summary.get("totalAnomalies", 0),
        "highRiskProjects": summary.get("highRiskProjects", 0),
        "timestamp": result.get("timestamp"),
    }


@shared_task(name="stripe_engine.auto_backup_all_projects")
@beat_singleton("auto_backup_all_projects", ttl_seconds=7200)
def auto_backup_all_projects_task() -> dict:
    """Automatically backup all projects before critical operations."""
    from apps.stripe_core.backup_recovery import create_project_backup

    project_ids = (
        VaultSecret.objects.filter(key_name="STRIPE_SECRET_KEY")
        .values_list("project_id", flat=True)
        .distinct()
    )

    backed_up = 0
    failed = 0

    for pid in project_ids:
        try:
            project = Project.objects.get(id=pid)
            result = create_project_backup(project)
            if result.success:
                backed_up += 1
            else:
                failed += 1
        except Project.DoesNotExist:
            failed += 1

    return {
        "backedUp": backed_up,
        "failed": failed,
        "total": len(project_ids),
    }
