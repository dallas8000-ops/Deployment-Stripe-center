"""URL configuration for stripe_engine app."""

from django.urls import path

from apps.stripe_engine import views

app_name = "stripe_engine"

urlpatterns = [
    path("projects/<uuid:project_id>/auto-heal/", views.auto_heal, name="auto-heal"),
    path("projects/<uuid:project_id>/auto-heal/recommendations/", views.auto_heal_recommendations, name="auto-heal-recommendations"),
    path("projects/<uuid:project_id>/predictive-analysis/", views.predictive_analysis, name="predictive-analysis"),
    path("projects/<uuid:project_id>/proactive-recommendations/", views.proactive_recommendations, name="proactive-recommendations"),
    path("projects/<uuid:project_id>/webhook-test-suite/", views.webhook_test_suite, name="webhook-test-suite"),
    path("projects/<uuid:project_id>/health-monitor/", views.health_monitor, name="health-monitor"),
    path("projects/<uuid:project_id>/schedule-recommendations/", views.schedule_recommendations, name="schedule-recommendations"),
    path("projects/<uuid:project_id>/optimize-schedule/", views.optimize_schedule, name="optimize-schedule"),
    path("projects/<uuid:project_id>/backup/", views.create_backup, name="create-backup"),
    path("projects/<uuid:project_id>/backups/", views.list_backups, name="list-backups"),
    path("projects/<uuid:project_id>/backup/restore/", views.restore_backup, name="restore-backup"),
    path("projects/<uuid:project_id>/backup/cleanup/", views.cleanup_backups, name="cleanup-backups"),
    path("projects/<uuid:project_id>/anomaly-detection/", views.anomaly_detection, name="anomaly-detection"),
    path("projects/<uuid:project_id>/performance-optimization/", views.performance_optimization, name="performance-optimization"),
    path("admin/health-monitor-all/", views.all_projects_health_monitor, name="all-projects-health-monitor"),
    path("admin/global-optimization/", views.global_optimization, name="global-optimization"),
    path("admin/anomaly-detection-all/", views.all_projects_anomaly_detection, name="all-projects-anomaly-detection"),
]
