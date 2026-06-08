from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin

from .crypto import VaultConfigurationError
from .import_env import import_env_to_vault
from .models import ProjectVault, delete_secret, get_or_create_vault, list_secret_keys, list_vault_entries, set_secret
from .serializers import VaultDeleteSerializer, VaultEntrySerializer, VaultImportSerializer, VaultKeyListSerializer, VaultSetSerializer


class VaultInitView(ProjectOwnedMixin, APIView):
    project_min_role = "admin"
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
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


class VaultKeysView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug, min_role="viewer")
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


class VaultSetView(ProjectOwnedMixin, APIView):
    project_min_role = "admin"
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
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


class VaultDeleteView(ProjectOwnedMixin, APIView):
    project_min_role = "admin"
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
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


class VaultImportView(ProjectOwnedMixin, APIView):
    project_min_role = "admin"
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        from pathlib import Path

        project = self.get_project(project_slug)
        if not project.local_path:
            return Response({"error": "Set project local_path first."}, status=status.HTTP_400_BAD_REQUEST)
        root = Path(project.local_path).resolve()
        if not root.is_dir():
            return Response({"error": f"Project path not found: {root}"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = VaultImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        env_file = serializer.validated_data.get("env_file", ".env.local")

        try:
            get_or_create_vault(project)
            imported = import_env_to_vault(project, root, env_file=env_file)
        except VaultConfigurationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except (FileNotFoundError, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "imported": imported,
                "env_file": env_file,
                "keys": list_secret_keys(project),
                "entries": list_vault_entries(project),
            },
            status=status.HTTP_201_CREATED,
        )
