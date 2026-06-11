"""API views for stripe_engine app."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai.predictive import get_proactive_recommendations, run_predictive_analysis
from apps.projects.models import Project
from apps.stripe_engine.anomaly_detection import run_all_projects_anomaly_detection, run_anomaly_detection
from apps.stripe_engine.auto_heal import HealPolicy, get_heal_recommendations, run_auto_heal
from apps.stripe_engine.backup_recovery import create_project_backup, cleanup_old_backups, list_project_backups, restore_project_backup
from apps.stripe_engine.health_monitor import run_all_projects_health_monitor, run_health_monitor
from apps.stripe_engine.intelligent_scheduler import get_global_optimization_recommendations, get_schedule_recommendations, optimize_celery_schedule
from apps.stripe_engine.performance_optimizer import run_performance_optimization_analysis
from apps.stripe_engine.webhook_tester import run_webhook_test_suite


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def auto_heal(request, project_id):
    """Run automated self-healing on a project."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    dry_run = request.data.get("dry_run", False)
    app_url = request.data.get("app_url", "http://localhost:8000")

    # Allow custom policy from request
    policy_data = request.data.get("policy")
    if policy_data:
        policy = HealPolicy(
            severity_threshold=policy_data.get("severity_threshold", "warning"),
            max_auto_fixes_per_run=policy_data.get("max_auto_fixes_per_run", 5),
            require_confirmation_for=policy_data.get("require_confirmation_for", []),
            safe_actions=policy_data.get("safe_actions"),
        )
    else:
        policy = None

    result = run_auto_heal(project, policy=policy, dry_run=dry_run, app_url=app_url)
    return Response(result.to_dict())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def auto_heal_recommendations(request, project_id):
    """Get recommendations for what can be auto-healed."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    recommendations = get_heal_recommendations(project)
    return Response({"recommendations": recommendations})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def predictive_analysis(request, project_id):
    """Run predictive analysis on a project."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    result = run_predictive_analysis(project)
    return Response(result.to_dict())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def proactive_recommendations(request, project_id):
    """Get proactive recommendations combining diagnostics, readiness, and predictions."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    result = get_proactive_recommendations(project)
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def webhook_test_suite(request, project_id):
    """Run automated webhook test suite."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    result = run_webhook_test_suite(project)
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def health_monitor(request, project_id):
    """Run comprehensive health monitoring on a project."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    report = run_health_monitor(project)
    return Response(report.to_dict())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_projects_health_monitor(request):
    """Run health monitoring on all projects (admin only)."""
    if not request.user.is_staff:
        return Response({"error": "Admin only"}, status=status.HTTP_403_FORBIDDEN)

    result = run_all_projects_health_monitor()
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def schedule_recommendations(request, project_id):
    """Get intelligent schedule recommendations for a project."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    recommendations = get_schedule_recommendations(project)
    return Response({"recommendations": [r.to_dict() for r in recommendations]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def optimize_schedule(request, project_id):
    """Get optimized Celery schedule for a project."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    result = optimize_celery_schedule(project)
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def global_optimization(request):
    """Get global optimization recommendations (admin only)."""
    if not request.user.is_staff:
        return Response({"error": "Admin only"}, status=status.HTTP_403_FORBIDDEN)

    result = get_global_optimization_recommendations()
    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_backup(request, project_id):
    """Create a backup of project configuration."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    result = create_project_backup(project)
    return Response(result.to_dict())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_backups(request, project_id):
    """List all backups for a project."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    backups = list_project_backups(project)
    return Response({"backups": backups})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def restore_backup(request, project_id):
    """Restore a project from backup."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    backup_id = request.data.get("backup_id")
    if not backup_id:
        return Response({"error": "backup_id required"}, status=status.HTTP_400_BAD_REQUEST)

    result = restore_project_backup(project, backup_id)
    return Response(result.to_dict())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cleanup_backups(request, project_id):
    """Clean up old backups."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    keep_days = request.data.get("keep_days", 30)
    result = cleanup_old_backups(project, keep_days=keep_days)
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def anomaly_detection(request, project_id):
    """Run anomaly detection on a project."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    report = run_anomaly_detection(project)
    return Response(report.to_dict())


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_projects_anomaly_detection(request):
    """Run anomaly detection on all projects (admin only)."""
    if not request.user.is_staff:
        return Response({"error": "Admin only"}, status=status.HTTP_403_FORBIDDEN)

    result = run_all_projects_anomaly_detection()
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def performance_optimization(request, project_id):
    """Run performance optimization analysis on a project."""
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

    result = run_performance_optimization_analysis(project)
    return Response(result)
