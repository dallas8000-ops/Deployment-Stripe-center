"""Org billing limits and subscription checks."""

from __future__ import annotations

from django.conf import settings

from apps.billing.models import OrgSubscription, Subscription


class BillingLimitError(Exception):
    def __init__(self, message: str, *, code: str = "upgrade_required"):
        super().__init__(message)
        self.code = code


def free_member_limit() -> int:
    return int(getattr(settings, "ORG_FREE_MEMBER_LIMIT", "3"))


def free_project_limit() -> int:
    return int(getattr(settings, "ORG_FREE_PROJECT_LIMIT", "5"))


def org_has_active_subscription(org) -> bool:
    try:
        return org.subscription.is_active
    except OrgSubscription.DoesNotExist:
        return False


def user_has_active_subscription(user) -> bool:
    try:
        return user.subscription.is_active
    except Subscription.DoesNotExist:
        return False


def org_billing_exempt(org) -> bool:
    """Paid org sub, or SaaS billing not configured (dev)."""
    if not getattr(settings, "SAAS_STRIPE_SECRET_KEY", ""):
        return True
    return org_has_active_subscription(org)


def assert_can_add_org_member(org) -> None:
    if org_billing_exempt(org):
        return
    if org.memberships.count() >= free_member_limit():
        raise BillingLimitError(
            f"Free tier allows {free_member_limit()} members. Subscribe on Billing → Organization billing.",
            code="org_member_limit",
        )


def assert_can_assign_org_project(org) -> None:
    if org_billing_exempt(org):
        return
    if org.projects.count() >= free_project_limit():
        raise BillingLimitError(
            f"Free tier allows {free_project_limit()} org projects. Subscribe on Billing → Organization billing.",
            code="org_project_limit",
        )
