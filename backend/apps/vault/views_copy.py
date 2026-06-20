"""Keys safe to reveal for clipboard copy (publishable + webhook — not sk_ secret)."""

from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin

from .models import get_secret, list_secret_keys

COPYABLE_VAULT_KEYS = frozenset(
    {
        "STRIPE_PUBLISHABLE_KEY",
        "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
        "STRIPE_WEBHOOK_SECRET",
    }
)


class VaultCopyView(ProjectOwnedMixin, APIView):
    """Return plaintext for copy-to-clipboard — publishable and webhook secrets only."""

    project_min_role = "admin"
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug, min_role="admin")
        key = (request.data.get("key") or "").strip()
        if not key:
            return Response({"error": "key is required"}, status=status.HTTP_400_BAD_REQUEST)
        if key not in COPYABLE_VAULT_KEYS:
            return Response(
                {
                    "error": (
                        f"{key} cannot be copied from the vault UI. "
                        "Secret keys (sk_live_) must be copied from Stripe Dashboard. "
                        "Use Sync keys to billing projects to copy server-side without displaying."
                    ),
                    "copyable": False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if key not in list_secret_keys(project):
            return Response({"error": f"{key} not in vault"}, status=status.HTTP_404_NOT_FOUND)
        value = get_secret(project, key)
        if not value:
            return Response(
                {"error": f"{key} is stored but unreadable — Replace or Import from .env"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"key": key, "value": value, "copyable": True})
