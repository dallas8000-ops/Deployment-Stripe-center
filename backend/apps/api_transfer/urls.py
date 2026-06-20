from django.urls import path

from .platform_views import PlatformSetupAuditView, PlatformSetupRunView
from .transfer_views import (
    ProjectTransferHistoryView,
    ProjectTransferStartView,
    TransferHistoryView,
    TransferMetricsView,
    TransferReplayView,
    TransferStartView,
    TransferStatusView,
    TransferStopView,
)
from .views import (
    AuditExportView,
    AuditView,
    DeployDetectView,
    GitHubImportView,
    ProjectDeployDetectView,
    ProjectDeployView,
    ProjectDeploymentHistoryView,
    ProjectDeploymentStatusRefreshView,
    ProjectGitHubImportView,
    ProviderStatusView,
    RailwayEnvBackupView,
    TransferModuleStatusView,
)

urlpatterns = [
    path("transfer/status/", TransferModuleStatusView.as_view(), name="transfer-module-status"),
    path("transfer/providers/status/", ProviderStatusView.as_view(), name="transfer-provider-status"),
    path("transfer/deploy/detect/", DeployDetectView.as_view(), name="transfer-deploy-detect"),
    path("transfer/github/import/", GitHubImportView.as_view(), name="transfer-github-import"),
    path("transfer/env/backup/railway/", RailwayEnvBackupView.as_view(), name="transfer-railway-env-backup"),
    path("transfer/audit/", AuditView.as_view(), name="transfer-audit"),
    path("transfer/audit/export/", AuditExportView.as_view(), name="transfer-audit-export"),
    path("transfer/start/", TransferStartView.as_view(), name="transfer-start"),
    path("transfer/stop/", TransferStopView.as_view(), name="transfer-stop"),
    path("transfer/runs/status/", TransferStatusView.as_view(), name="transfer-runs-status"),
    path("transfer/runs/history/", TransferHistoryView.as_view(), name="transfer-runs-history"),
    path("transfer/runs/metrics/", TransferMetricsView.as_view(), name="transfer-runs-metrics"),
    path("transfer/runs/replay/<str:run_id>/", TransferReplayView.as_view(), name="transfer-runs-replay"),
    path("transfer/platform/setup-audit/", PlatformSetupAuditView.as_view(), name="transfer-platform-setup-audit"),
    path("transfer/platform/setup-run/", PlatformSetupRunView.as_view(), name="transfer-platform-setup-run"),
    path(
        "projects/<slug:project_slug>/transfer/github/import/",
        ProjectGitHubImportView.as_view(),
        name="project-transfer-github-import",
    ),
    path(
        "projects/<slug:project_slug>/transfer/deploy/detect/",
        ProjectDeployDetectView.as_view(),
        name="project-transfer-deploy-detect",
    ),
    path(
        "projects/<slug:project_slug>/transfer/deploy/",
        ProjectDeployView.as_view(),
        name="project-transfer-deploy",
    ),
    path(
        "projects/<slug:project_slug>/transfer/deploy/history/",
        ProjectDeploymentHistoryView.as_view(),
        name="project-transfer-deploy-history",
    ),
    path(
        "projects/<slug:project_slug>/transfer/deploy/status/<str:deployment_id>/",
        ProjectDeploymentStatusRefreshView.as_view(),
        name="project-transfer-deploy-status",
    ),
    path(
        "projects/<slug:project_slug>/transfer/start/",
        ProjectTransferStartView.as_view(),
        name="project-transfer-start",
    ),
    path(
        "projects/<slug:project_slug>/transfer/runs/history/",
        ProjectTransferHistoryView.as_view(),
        name="project-transfer-runs-history",
    ),
]
