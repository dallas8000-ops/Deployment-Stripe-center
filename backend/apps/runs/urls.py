from django.urls import path

from apps.stripe_installer.views_setup_hub import SetupHubActionView, SetupHubView

from .views import (
    CodegenDownloadView,
    PipelineRunDetailView,
    PipelineRunDownloadView,
    PipelineRunListCreateView,
    StripeAdvisorView,
    StripeConfigView,
    VerifyKeysView,
)

urlpatterns = [
    path(
        "projects/<slug:project_slug>/verify/",
        VerifyKeysView.as_view(),
        name="project-verify",
    ),
    path(
        "projects/<slug:project_slug>/runs/",
        PipelineRunListCreateView.as_view(),
        name="pipeline-run-list",
    ),
    path(
        "projects/<slug:project_slug>/runs/<uuid:run_id>/",
        PipelineRunDetailView.as_view(),
        name="pipeline-run-detail",
    ),
    path(
        "projects/<slug:project_slug>/runs/<uuid:run_id>/download/",
        PipelineRunDownloadView.as_view(),
        name="pipeline-run-download",
    ),
    path(
        "projects/<slug:project_slug>/codegen/download/",
        CodegenDownloadView.as_view(),
        name="codegen-download",
    ),
    path(
        "projects/<slug:project_slug>/stripe-advisor/",
        StripeAdvisorView.as_view(),
        name="project-stripe-advisor",
    ),
    path(
        "projects/<slug:project_slug>/stripe/config/",
        StripeConfigView.as_view(),
        name="stripe-config",
    ),
    path(
        "projects/<slug:project_slug>/setup-hub/",
        SetupHubView.as_view(),
        name="project-setup-hub",
    ),
    path(
        "projects/<slug:project_slug>/setup-hub/actions/",
        SetupHubActionView.as_view(),
        name="project-setup-hub-actions",
    ),
]
