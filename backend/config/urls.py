from django.contrib import admin
from django.urls import include, path, re_path

from apps.projects.ci_views import CiReadinessGateView
from apps.projects.github_webhook_views import github_webhook

from .spa import spa_asset, spa_index
from .views import health, root

urlpatterns = [
    path("", root),
    path("health/", health),
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.organizations.urls")),
    path("api/v1/ci/readiness/", CiReadinessGateView.as_view(), name="ci-readiness-gate"),
    path("api/v1/webhooks/github/", github_webhook, name="github-webhook"),
    path("api/v1/projects/", include("apps.projects.urls")),
    path("api/v1/", include("apps.vault.urls")),
    path("api/v1/", include("apps.runs.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.deploy.urls")),
    path("api/v1/", include("apps.ai.urls")),
    path("api/v1/", include("apps.licenses.urls")),
    path("api/v1/", include("apps.stripe_engine.urls")),
    re_path(r"^assets/(?P<path>.+)$", spa_asset),
    re_path(r"^(?!api/|admin/|health/|static/|assets/|ws/).*$", spa_index),
]