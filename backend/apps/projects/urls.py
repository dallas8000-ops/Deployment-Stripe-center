from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .ci_views import ProjectCiWorkflowView, ProjectGithubCiView, ProjectReadinessGateView
from .views import ProjectViewSet

router = DefaultRouter()
router.register("", ProjectViewSet, basename="project")

urlpatterns = [
    path(
        "<slug:project_slug>/github/ci-status/",
        ProjectGithubCiView.as_view(),
        name="project-github-ci-status",
    ),
    path(
        "<slug:project_slug>/ci/workflow/",
        ProjectCiWorkflowView.as_view(),
        name="project-ci-workflow",
    ),
    path(
        "<slug:project_slug>/ci/readiness-gate/",
        ProjectReadinessGateView.as_view(),
        name="project-readiness-gate",
    ),
    path("", include(router.urls)),
]
