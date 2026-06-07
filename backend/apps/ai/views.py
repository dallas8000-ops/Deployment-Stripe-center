from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project
from django.shortcuts import get_object_or_404

from .services import local_recommendations


class RecommendView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = get_object_or_404(Project, slug=project_slug, owner=request.user)
        try:
            text = local_recommendations(project)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"recommendations": text, "provider": "local"})
