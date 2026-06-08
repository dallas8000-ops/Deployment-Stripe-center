"""Organization email invites — register link + optional SMTP."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.billing.enforcement import BillingLimitError, assert_can_add_org_member

from .models import Membership, Organization, OrganizationInvite

User = get_user_model()


def app_base_url() -> str:
    return getattr(settings, "APP_PUBLIC_URL", "") or getattr(
        settings, "SAAS_BILLING_RETURN_URL", "http://localhost:5173"
    ).rstrip("/")


def invite_register_url(token: str) -> str:
    return f"{app_base_url()}/register?invite={token}"


def get_pending_invite(token: str) -> OrganizationInvite | None:
    invite = OrganizationInvite.objects.filter(token=token).select_related("organization").first()
    if not invite or not invite.is_pending:
        return None
    return invite


def invite_preview(token: str) -> dict:
    invite = get_pending_invite(token)
    if not invite:
        return {"valid": False}
    return {
        "valid": True,
        "email": invite.email,
        "role": invite.role,
        "organization": invite.organization.name,
        "organizationSlug": invite.organization.slug,
        "expiresAt": invite.expires_at.isoformat(),
    }


def send_invite_email(invite: OrganizationInvite) -> bool:
    if not getattr(settings, "INVITE_EMAIL_ENABLED", True):
        return False
    url = invite_register_url(invite.token)
    subject = f"Join {invite.organization.name} on Stripe Installer"
    body = (
        f"You've been invited to join {invite.organization.name} as {invite.role}.\n\n"
        f"Create your account:\n{url}\n\n"
        f"This link expires {invite.expires_at.strftime('%Y-%m-%d %H:%M UTC')}."
    )
    try:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost"),
            [invite.email],
            fail_silently=False,
        )
        return True
    except Exception:
        return False


@transaction.atomic
def invite_to_org(org: Organization, *, email: str, role: str, invited_by) -> dict:
    email = email.strip().lower()
    assert_can_add_org_member(org)

    existing_user = User.objects.filter(email__iexact=email).first()
    if existing_user:
        if org.memberships.filter(user=existing_user).exists():
            raise ValueError("User is already a member")
        membership = Membership.objects.create(organization=org, user=existing_user, role=role)
        return {"status": "joined", "membership": membership}

    pending = OrganizationInvite.objects.filter(
        organization=org, email__iexact=email, accepted_at__isnull=True
    ).first()
    if pending:
        pending.role = role
        pending.token = OrganizationInvite.generate_token()
        pending.expires_at = OrganizationInvite.default_expiry()
        pending.invited_by = invited_by
        pending.save()
        invite = pending
    else:
        invite = OrganizationInvite.objects.create(
            organization=org,
            email=email,
            role=role,
            invited_by=invited_by,
            token=OrganizationInvite.generate_token(),
            expires_at=OrganizationInvite.default_expiry(),
        )

    email_sent = send_invite_email(invite)
    return {
        "status": "pending",
        "invite": invite,
        "inviteUrl": invite_register_url(invite.token),
        "emailSent": email_sent,
    }


@transaction.atomic
def accept_invite(token: str, user) -> Membership | None:
    invite = OrganizationInvite.objects.select_for_update().filter(token=token).first()
    if not invite or not invite.is_pending:
        return None
    if user.email.lower() != invite.email.lower():
        raise ValueError("Invite email does not match your account email")

    if invite.organization.memberships.filter(user=user).exists():
        invite.accepted_at = timezone.now()
        invite.save(update_fields=["accepted_at"])
        return invite.organization.memberships.filter(user=user).first()

    try:
        assert_can_add_org_member(invite.organization)
    except BillingLimitError as exc:
        raise ValueError(str(exc)) from exc

    membership = Membership.objects.create(
        organization=invite.organization,
        user=user,
        role=invite.role,
    )
    invite.accepted_at = timezone.now()
    invite.save(update_fields=["accepted_at"])
    return membership
