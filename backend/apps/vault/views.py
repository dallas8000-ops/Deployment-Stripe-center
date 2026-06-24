from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin
from apps.stripe_core.hub_keys import pull_stripe_keys_for_user

from .crypto import VaultConfigurationError
from .import_env import auto_import_env_to_vault, find_env_file, import_env_to_vault
from .models import ProjectVault, delete_secret, get_or_create_vault, hydrate_project_vault, list_secret_keys, list_vault_entries, set_secret, vault_health
from .serializers import (
    VaultDeleteSerializer,
    VaultEntrySerializer,
    VaultImportAllSerializer,
    VaultImportSerializer,
    VaultKeyListSerializer,
    VaultSetSerializer,
)
from .secret_sources import discover_secret_sources, import_all_discovered_secrets, resolve_project_root


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
                "vaultHealth": vault_health(project),
            },
            status=status.HTTP_201_CREATED,
        )


class VaultKeysView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug, min_role="viewer")
        hydrate_project_vault(project)
        pull_stripe_keys_for_user(project, request.user)
        initialized = ProjectVault.objects.filter(project=project).exists()
        entries = list_vault_entries(project)
        data = VaultKeyListSerializer(
            {
                "keys": [e["key"] for e in entries],
                "entries": entries,
                "initialized": initialized,
                "vaultHealth": vault_health(project),
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
        root = resolve_project_root(project)
        if not root:
            return Response(
                {
                    "error": (
                        "Project folder not found. Set local_path on the project or add "
                        "localPath in ~/.stripe-installer/portfolio-registry.json"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VaultImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        env_file = serializer.validated_data.get("env_file", "auto").strip() or "auto"

        try:
            get_or_create_vault(project)
            imported = import_env_to_vault(project, root, env_file=env_file)
            if env_file == "auto":
                found = find_env_file(root)
                env_file = found.relative_to(root).as_posix() if found else "auto"
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
                "vaultHealth": vault_health(project),
            },
            status=status.HTTP_201_CREATED,
        )


class VaultSourcesView(ProjectOwnedMixin, APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, project_slug: str):
        project = self.get_project(project_slug, min_role="viewer")
        return Response(discover_secret_sources(project))


class VaultImportAllView(ProjectOwnedMixin, APIView):
    project_min_role = "admin"
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug)
        serializer = VaultImportAllSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        root = resolve_project_root(project)
        if not root:
            return Response(
                {
                    "error": (
                        "Project folder not found. Set local_path on the project or add "
                        "localPath in ~/.stripe-installer/portfolio-registry.json"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            get_or_create_vault(project)
            result = import_all_discovered_secrets(
                project,
                legacy_passphrase=serializer.validated_data.get("legacy_passphrase"),
                include_legacy=serializer.validated_data.get("include_legacy", True),
                include_env=serializer.validated_data.get("include_env", True),
            )
        except VaultConfigurationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            {
                **result,
                "keys": list_secret_keys(project),
                "entries": list_vault_entries(project),
                "vaultHealth": vault_health(project),
            },
            status=status.HTTP_201_CREATED,
        )
