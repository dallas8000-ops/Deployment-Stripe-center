from django.urls import path

from .views import PostgresSchemaView, PostgresStatusView

urlpatterns = [
    path(
        "projects/<slug:project_slug>/postgres/status/",
        PostgresStatusView.as_view(),
        name="postgres-status",
    ),
    path(
        "projects/<slug:project_slug>/postgres/schema/",
        PostgresSchemaView.as_view(),
        name="postgres-schema",
    ),
]
