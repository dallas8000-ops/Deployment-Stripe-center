from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project
from django.shortcuts import get_object_or_404

from .postgres import postgres_status, schema_sql


class ProjectOwnedMixin:
    def get_project(self, project_slug: str) -> Project:
        return get_object_or_404(Project, slug=project_slug, owner=self.request.user)


class PostgresStatusView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug)
        return Response(postgres_status(project))


class PostgresSchemaView(ProjectOwnedMixin, APIView):
    """Return schema SQL for manual or CI apply — does not connect to client DB from SaaS."""

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        self.get_project(project_slug)
        return Response({"schema": schema_sql()})
