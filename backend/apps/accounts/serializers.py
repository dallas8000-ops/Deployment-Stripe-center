from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    mfa_enabled = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "display_name", "date_joined", "mfa_enabled")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    invite_token = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ("email", "password", "display_name", "invite_token")

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate(self, attrs):
        token = (attrs.get("invite_token") or "").strip()
        if token:
            from apps.organizations.invites import get_pending_invite

            invite = get_pending_invite(token)
            if not invite:
                raise serializers.ValidationError({"invite_token": "Invite link is invalid or expired."})
            if invite.email.lower() != attrs["email"].strip().lower():
                raise serializers.ValidationError(
                    {"email": f"Use the invited email address ({invite.email})."}
                )
            attrs["_invite"] = invite
        return attrs

    def create(self, validated_data):
        invite = validated_data.pop("_invite", None)
        validated_data.pop("invite_token", None)
        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            display_name=validated_data.get("display_name", ""),
        )
        if invite:
            from apps.organizations.invites import accept_invite

            accept_invite(invite.token, user)
        return user
