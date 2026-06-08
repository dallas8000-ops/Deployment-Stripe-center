from rest_framework import serializers

from apps.accounts.models import User

from .models import Membership, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "slug",
            "created_at",
            "updated_at",
            "member_count",
            "my_role",
            "github_installation_id",
            "github_account",
        )
        read_only_fields = (
            "id",
            "slug",
            "created_at",
            "updated_at",
            "member_count",
            "my_role",
            "github_installation_id",
            "github_account",
        )

    def get_member_count(self, obj: Organization) -> int:
        return obj.memberships.count()

    def get_my_role(self, obj: Organization) -> str | None:
        user = self.context["request"].user
        membership = obj.memberships.filter(user=user).first()
        return membership.role if membership else None


class MembershipSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    display_name = serializers.CharField(source="user.display_name", read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "email", "display_name", "role", "invited_at")


class InviteMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Membership.Role.choices, default=Membership.Role.MEMBER)


class UpdateMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices)


class LinkGithubInstallationSerializer(serializers.Serializer):
    installation_id = serializers.IntegerField(min_value=1)
    github_account = serializers.CharField(required=False, allow_blank=True, max_length=200)


class OrganizationInviteSerializer(serializers.ModelSerializer):
    invite_url = serializers.SerializerMethodField()
    invited_by_email = serializers.EmailField(source="invited_by.email", read_only=True)

    class Meta:
        from .models import OrganizationInvite

        model = OrganizationInvite
        fields = (
            "id",
            "email",
            "role",
            "created_at",
            "expires_at",
            "accepted_at",
            "invite_url",
            "invited_by_email",
        )
        read_only_fields = fields

    def get_invite_url(self, obj) -> str:
        from .invites import invite_register_url

        return invite_register_url(obj.token)


class CompleteGithubInstallSerializer(serializers.Serializer):
    installation_id = serializers.IntegerField(min_value=1)
    state = serializers.CharField(required=False, allow_blank=True, max_length=200)
    setup_action = serializers.CharField(required=False, allow_blank=True, max_length=64)
