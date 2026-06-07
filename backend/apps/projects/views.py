from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Project
from .scanner import ProjectScanner
from .serializers import ProjectScanSerializer, ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "slug"

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=["post"])
    def scan(self, request, slug=None):
        project = self.get_object()
        body = ProjectScanSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        scan_path = body.validated_data.get("local_path") or project.local_path
        if not scan_path:
            return Response(
                {"error": "Set local_path on the project or pass local_path in the request body."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if body.validated_data.get("local_path"):
            project.local_path = scan_path
            project.save(update_fields=["local_path", "updated_at"])

        try:
            result = ProjectScanner(scan_path).scan()
        except FileNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        data = result.to_dict()
        project.framework = data["framework"]
        project.language = data["language"]
        project.scan_data = data
        project.last_scanned_at = timezone.now()
        project.save(
            update_fields=["framework", "language", "scan_data", "last_scanned_at", "updated_at"]
        )

        return Response(ProjectSerializer(project).data)
