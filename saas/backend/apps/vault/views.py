from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project

from .crypto import VaultConfigurationError
from .models import ProjectVault, delete_secret, get_or_create_vault, list_secret_keys, list_vault_entries, set_secret
from .serializers import VaultDeleteSerializer, VaultEntrySerializer, VaultKeyListSerializer, VaultSetSerializer


class ProjectVaultMixin:
    def get_project(self, request, project_slug: str) -> Project:
        return get_object_or_404(Project, slug=project_slug, owner=request.user)


class VaultInitView(ProjectVaultMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(request, project_slug)
        try:
            vault = get_or_create_vault(project)
        except VaultConfigurationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(
            {
                "initialized": True,
                "initialized_at": vault.initialized_at.isoformat(),
                "keys": list_secret_keys(project),
                "entries": list_vault_entries(project),
            },
            status=status.HTTP_201_CREATED,
        )


class VaultKeysView(ProjectVaultMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(request, project_slug)
        initialized = ProjectVault.objects.filter(project=project).exists()
        entries = list_vault_entries(project)
        data = VaultKeyListSerializer(
            {
                "keys": [e["key"] for e in entries],
                "entries": entries,
                "initialized": initialized,
            }
        ).data
        return Response(data)


class VaultSetView(ProjectVaultMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(request, project_slug)
        serializer = VaultSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data["key"]
        try:
            secret = set_secret(project, key, serializer.validated_data["value"])
        except VaultConfigurationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        entry = VaultEntrySerializer(secret.to_entry_dict()).data
        return Response(
            {
                "stored": key,
                "keys": list_secret_keys(project),
                "entries": list_vault_entries(project),
                "entry": entry,
            },
            status=status.HTTP_201_CREATED,
        )


class VaultDeleteView(ProjectVaultMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(request, project_slug)
        serializer = VaultDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializer.validated_data["key"]
        if key not in list_secret_keys(project):
            return Response({"error": f"{key} not found in vault."}, status=status.HTTP_404_NOT_FOUND)
        delete_secret(project, key)
        return Response(
            {
                "deleted": key,
                "keys": list_secret_keys(project),
                "entries": list_vault_entries(project),
            }
        )
