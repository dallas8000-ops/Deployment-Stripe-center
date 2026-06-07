from django.contrib import admin
from django.urls import include, path

from .views import health, root

urlpatterns = [
    path("", root),
    path("health/", health),
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/projects/", include("apps.projects.urls")),
    path("api/v1/", include("apps.vault.urls")),
    path("api/v1/", include("apps.runs.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.deploy.urls")),
    path("api/v1/", include("apps.ai.urls")),
]
