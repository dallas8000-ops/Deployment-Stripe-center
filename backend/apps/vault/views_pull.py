from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.access import ProjectOwnedMixin
from apps.stripe_installer.hub_keys import HUB_SLUG, pull_stripe_keys_for_user
from apps.stripe_installer.portfolio_catalog import is_stripe_exempt_slug

from .models import get_or_create_vault, get_secret, list_secret_keys, list_vault_entries, vault_health


class VaultPullFromHubView(ProjectOwnedMixin, APIView):
    project_min_role = "admin"
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, project_slug: str):
        project = self.get_project(project_slug, min_role="admin")
        if project.slug == HUB_SLUG:
            return Response({"copied": [], "message": "This is the hub project — add keys here first."})
        if is_stripe_exempt_slug(project.slug):
            return Response(
                {"copied": [], "message": "Portfolio demo — no Stripe billing keys needed."},
            )

        get_or_create_vault(project)
        copied = pull_stripe_keys_for_user(project, request.user)
        existing = list_secret_keys(project)
        if not copied:
            if get_secret(project, "STRIPE_SECRET_KEY"):
                return Response(
                    {
                        "copied": [],
                        "message": "Keys already present — no new keys copied from Automation Center.",
                        "keys": existing,
                        "entries": list_vault_entries(project),
                        "vaultHealth": vault_health(project),
                    }
                )
            return Response(
                {
                    "copied": [],
                    "message": (
                        "No keys copied — add STRIPE_SECRET_KEY on Deployment & Stripe Automation Center first."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "copied": copied,
                "message": f"Pulled {len(copied)} key(s) from Automation Center.",
                "keys": list_secret_keys(project),
                "entries": list_vault_entries(project),
                "vaultHealth": vault_health(project),
            }
        )
