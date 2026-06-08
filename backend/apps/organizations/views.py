from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.enforcement import (
    BillingLimitError,
    assert_can_add_org_member,
    free_member_limit,
    free_project_limit,
    org_billing_exempt,
    org_has_active_subscription,
)
from apps.core.access import ROLE_RANK, org_membership, projects_for_user

from .github_install import (
    apply_installation,
    build_install_url,
    github_app_configured,
    parse_install_state,
    verify_installation,
)
from .invites import invite_preview, invite_to_org
from .models import Membership, Organization, OrganizationInvite
from .serializers import (
    CompleteGithubInstallSerializer,
    InviteMemberSerializer,
    LinkGithubInstallationSerializer,
    MembershipSerializer,
    OrganizationInviteSerializer,
    OrganizationSerializer,
    UpdateMemberRoleSerializer,
)

User = get_user_model()


def _require_org_role(user, organization, min_role: str) -> Membership:
    membership = org_membership(user, organization)
    if not membership or ROLE_RANK.get(membership.role, -1) < ROLE_RANK.get(min_role, 99):
        return None
    return membership


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = "slug"

    def get_queryset(self):
        return Organization.objects.filter(memberships__user=self.request.user).distinct()

    @transaction.atomic
    def perform_create(self, serializer):
        org = serializer.save(created_by=self.request.user)
        Membership.objects.create(
            organization=org,
            user=self.request.user,
            role=Membership.Role.OWNER,
        )

    def destroy(self, request, *args, **kwargs):
        org = self.get_object()
        membership = _require_org_role(request.user, org, "owner")
        if not membership:
            return Response({"error": "Only org owners can delete the organization"}, status=403)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def members(self, request, slug=None):
        org = self.get_object()
        if not org_membership(request.user, org):
            return Response({"error": "Not a member"}, status=403)
        rows = org.memberships.select_related("user").all()
        return Response({"members": MembershipSerializer(rows, many=True).data})

    @action(detail=True, methods=["post"], url_path="invite")
    def invite(self, request, slug=None):
        org = self.get_object()
        if not _require_org_role(request.user, org, "admin"):
            return Response({"error": "Admin role required"}, status=403)

        body = InviteMemberSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = invite_to_org(
                org,
                email=body.validated_data["email"],
                role=body.validated_data["role"],
                invited_by=request.user,
            )
        except BillingLimitError as exc:
            return Response({"error": str(exc), "code": exc.code}, status=402)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        from apps.projects.audit import log_audit

        if result["status"] == "joined":
            membership = result["membership"]
            for project in org.projects.all()[:1]:
                log_audit(
                    project,
                    "org.member_invited",
                    actor=request.user,
                    detail={"email": membership.user.email, "role": membership.role},
                )
                break
            return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)

        invite = result["invite"]
        return Response(
            {
                "pending": True,
                "email": invite.email,
                "role": invite.role,
                "inviteUrl": result["inviteUrl"],
                "emailSent": result["emailSent"],
                "invite": OrganizationInviteSerializer(invite).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="pending-invites")
    def pending_invites(self, request, slug=None):
        org = self.get_object()
        if not _require_org_role(request.user, org, "admin"):
            return Response({"error": "Admin role required"}, status=403)
        rows = org.invites.filter(accepted_at__isnull=True).order_by("-created_at")
        return Response({"invites": OrganizationInviteSerializer(rows, many=True).data})

    @action(detail=True, methods=["delete"], url_path=r"pending-invites/(?P<invite_id>[^/.]+)")
    def revoke_invite(self, request, slug=None, invite_id=None):
        org = self.get_object()
        if not _require_org_role(request.user, org, "admin"):
            return Response({"error": "Admin role required"}, status=403)
        invite = get_object_or_404(OrganizationInvite, id=invite_id, organization=org, accepted_at__isnull=True)
        invite.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch", "delete"], url_path=r"members/(?P<member_id>[^/.]+)")
    def member_detail(self, request, slug=None, member_id=None):
        """PATCH role or DELETE member — single route (DRF cannot register two actions on same path)."""
        org = self.get_object()
        if not _require_org_role(request.user, org, "admin"):
            return Response({"error": "Admin role required"}, status=403)

        membership = get_object_or_404(Membership, id=member_id, organization=org)

        if request.method == "DELETE":
            if membership.role == Membership.Role.OWNER:
                owners = org.memberships.filter(role=Membership.Role.OWNER).count()
                if owners <= 1:
                    return Response({"error": "Cannot remove the last owner"}, status=400)
            membership.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        body = UpdateMemberRoleSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        new_role = body.validated_data["role"]
        if membership.role == Membership.Role.OWNER and new_role != Membership.Role.OWNER:
            owners = org.memberships.filter(role=Membership.Role.OWNER).count()
            if owners <= 1:
                return Response({"error": "Cannot demote the last owner"}, status=400)
        membership.role = new_role
        membership.save(update_fields=["role"])
        return Response(MembershipSerializer(membership).data)

    @action(detail=True, methods=["post"], url_path="link-github")
    def link_github(self, request, slug=None):
        org = self.get_object()
        if not _require_org_role(request.user, org, "admin"):
            return Response({"error": "Admin role required"}, status=403)

        body = LinkGithubInstallationSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        org.github_installation_id = body.validated_data["installation_id"]
        org.github_account = body.validated_data.get("github_account") or org.github_account
        org.save(update_fields=["github_installation_id", "github_account", "updated_at"])
        return Response(OrganizationSerializer(org, context={"request": request}).data)

    @action(detail=True, methods=["get"], url_path="github/install-url")
    def github_install_url(self, request, slug=None):
        org = self.get_object()
        if not _require_org_role(request.user, org, "admin"):
            return Response({"error": "Admin role required"}, status=403)
        if not github_app_configured():
            return Response(
                {
                    "configured": False,
                    "message": "Set GITHUB_APP_SLUG in server .env (see backend/.env.example)",
                    "manual": True,
                }
            )
        return Response({"configured": True, **build_install_url(org)})

    @action(detail=True, methods=["post"], url_path="github/complete-install")
    def github_complete_install(self, request, slug=None):
        org = self.get_object()
        if not _require_org_role(request.user, org, "admin"):
            return Response({"error": "Admin role required"}, status=403)

        body = CompleteGithubInstallSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        installation_id = body.validated_data["installation_id"]
        state = (body.validated_data.get("state") or "").strip()
        if state:
            state_org = parse_install_state(state)
            if state_org and state_org != org.slug:
                return Response({"error": "Install state does not match organization"}, status=400)

        try:
            info = verify_installation(installation_id)
        except RuntimeError as exc:
            return Response({"error": str(exc)}, status=400)

        account_login = info.get("accountLogin") or ""
        apply_installation(org, installation_id, account_login)
        return Response(OrganizationSerializer(org, context={"request": request}).data)

    @action(detail=True, methods=["get"])
    def projects(self, request, slug=None):
        org = self.get_object()
        if not org_membership(request.user, org):
            return Response({"error": "Not a member"}, status=403)
        from apps.projects.serializers import ProjectSerializer

        qs = org.projects.all()
        return Response({"projects": ProjectSerializer(qs, many=True).data})


class InvitePreviewView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, token: str):
        return Response(invite_preview(token))


class AgencyDashboardView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        orgs = Organization.objects.filter(memberships__user=request.user).distinct()
        projects = projects_for_user(request.user).distinct()
        from apps.projects.serializers import ProjectSerializer

        return Response(
            {
                "organizations": OrganizationSerializer(
                    orgs, many=True, context={"request": request}
                ).data,
                "projects": ProjectSerializer(projects, many=True).data,
                "stats": {
                    "organizationCount": orgs.count(),
                    "projectCount": projects.count(),
                },
                "billing": {
                    "saasConfigured": bool(getattr(settings, "SAAS_STRIPE_SECRET_KEY", "")),
                    "freeMemberLimit": free_member_limit(),
                    "freeProjectLimit": free_project_limit(),
                    "organizations": [
                        {
                            "slug": org.slug,
                            "subscriptionActive": org_has_active_subscription(org) or org_billing_exempt(org),
                            "memberCount": org.memberships.count(),
                            "projectCount": org.projects.count(),
                        }
                        for org in orgs
                    ],
                },
            }
        )
