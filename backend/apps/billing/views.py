"""Platform billing — Stripe Installer SaaS subscriptions (dogfooding our own output)."""

from __future__ import annotations

from datetime import datetime, timezone

import stripe
from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import OrgSubscription, Subscription


def _stripe_configured() -> bool:
    return bool(getattr(settings, "SAAS_STRIPE_SECRET_KEY", ""))


def _get_stripe():
    stripe.api_key = settings.SAAS_STRIPE_SECRET_KEY
    stripe.api_version = settings.STRIPE_API_VERSION
    return stripe


def _plans() -> list[dict]:
    plans = []
    for tier, price_id, label, amount in (
        ("Starter", getattr(settings, "SAAS_STRIPE_PRICE_STARTER", ""), "Starter", 7900),
        ("Pro", getattr(settings, "SAAS_STRIPE_PRICE_PRO", ""), "Pro", 7900),
        ("Enterprise", getattr(settings, "SAAS_STRIPE_PRICE_ENTERPRISE", ""), "Enterprise", 7900),
    ):
        if price_id:
            plans.append(
                {
                    "tier": tier,
                    "priceId": price_id,
                    "label": label,
                    "amount": amount,
                    "currency": "usd",
                }
            )
    return plans


def _allowed_price_ids() -> set[str]:
    return {plan["priceId"] for plan in _plans()}


def _get_or_create_subscription(user) -> Subscription:
    sub, _ = Subscription.objects.get_or_create(user=user)
    return sub


def _get_or_create_org_subscription(org) -> OrgSubscription:
    sub, _ = OrgSubscription.objects.get_or_create(organization=org)
    return sub


class OrgSubscriptionView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        org_slug = request.query_params.get("org")
        if not org_slug:
            return Response({"error": "org query param required"}, status=400)

        from apps.core.access import org_membership
        from apps.organizations.models import Organization

        org = Organization.objects.filter(slug=org_slug).first()
        if not org or not org_membership(request.user, org):
            return Response({"error": "Not a member of this organization"}, status=403)

        sub = _get_or_create_org_subscription(org)
        return Response(
            {
                "organization": org.slug,
                "tier": sub.tier or None,
                "status": sub.status,
                "isActive": sub.is_active,
                "currentPeriodEnd": sub.current_period_end.isoformat() if sub.current_period_end else None,
                "cancelAtPeriodEnd": sub.cancel_at_period_end,
                "customerId": sub.stripe_customer_id or None,
            }
        )


class OrgCheckoutView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        if not _stripe_configured():
            return Response(
                {"error": "Platform billing is not configured (SAAS_STRIPE_SECRET_KEY)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        org_slug = request.data.get("org") or request.data.get("organization_slug")
        price_id = request.data.get("priceId") or request.data.get("price_id")
        domain_value = request.data.get("domain")
        if not isinstance(org_slug, str) or not isinstance(price_id, str):
            return Response({"error": "org and priceId required"}, status=400)
        if not isinstance(domain_value, str):
            return Response({"error": "domain required for license issuance"}, status=400)
        domain = domain_value.strip()
        if price_id not in _allowed_price_ids():
            return Response({"error": "Unknown or unavailable plan"}, status=400)
        if not domain:
            return Response({"error": "domain required for license issuance"}, status=400)

        from apps.licenses.utils import normalize_domain, validate_domain_format

        domain = normalize_domain(domain)
        if not validate_domain_format(domain):
            return Response({"error": "Invalid domain format"}, status=400)

        from apps.core.access import ROLE_RANK, org_membership
        from apps.organizations.models import Organization

        org = Organization.objects.filter(slug=org_slug).first()
        membership = org_membership(request.user, org) if org else None
        if not membership or ROLE_RANK.get(membership.role, -1) < ROLE_RANK["owner"]:
            return Response({"error": "Org owner role required"}, status=403)

        app_url = getattr(settings, "SAAS_BILLING_RETURN_URL", "http://localhost:5173")
        _get_stripe()
        sub = _get_or_create_org_subscription(org)

        session_params: dict = {
            "mode": "subscription",
            "customer_email": request.user.email,
            "client_reference_id": f"org:{org.pk}",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": f"{app_url.rstrip('/')}/billing?success=1&org={org.slug}",
            "cancel_url": f"{app_url.rstrip('/')}/billing?canceled=1&org={org.slug}",
            "metadata": {
                "organization_id": str(org.pk),
                "organization_slug": org.slug,
                "domain": domain,
            },
            "subscription_data": {
                "metadata": {
                    "organization_id": str(org.pk),
                    "organization_slug": org.slug,
                    "domain": domain,
                },
            },
        }
        if sub.stripe_customer_id:
            session_params["customer"] = sub.stripe_customer_id
            del session_params["customer_email"]

        session = stripe.checkout.Session.create(**session_params)
        return Response({"url": session.url})


class OrgPortalView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        if not _stripe_configured():
            return Response({"error": "Platform billing is not configured."}, status=503)

        org_slug = request.data.get("org") or request.data.get("organization_slug")
        if not org_slug:
            return Response({"error": "org required"}, status=400)

        from apps.core.access import ROLE_RANK, org_membership
        from apps.organizations.models import Organization

        org = Organization.objects.filter(slug=org_slug).first()
        membership = org_membership(request.user, org) if org else None
        if not membership or ROLE_RANK.get(membership.role, -1) < ROLE_RANK["admin"]:
            return Response({"error": "Org admin role required"}, status=403)

        sub = _get_or_create_org_subscription(org)
        if not sub.stripe_customer_id:
            return Response({"error": "No billing account yet — subscribe first."}, status=400)

        app_url = getattr(settings, "SAAS_BILLING_RETURN_URL", "http://localhost:5173")
        _get_stripe()
        session = stripe.billingPortal.Session.create(
            customer=sub.stripe_customer_id,
            return_url=f"{app_url.rstrip('/')}/billing?org={org.slug}",
        )
        return Response({"url": session.url})


class PlansView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        return Response(
            {
                "configured": _stripe_configured(),
                "plans": _plans(),
            }
        )


class SubscriptionView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        sub = _get_or_create_subscription(request.user)
        return Response(
            {
                "tier": sub.tier or None,
                "status": sub.status,
                "isActive": sub.is_active,
                "currentPeriodEnd": sub.current_period_end.isoformat() if sub.current_period_end else None,
                "cancelAtPeriodEnd": sub.cancel_at_period_end,
                "customerId": sub.stripe_customer_id or None,
            }
        )


class CheckoutView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        if not _stripe_configured():
            return Response(
                {"error": "Platform billing is not configured (SAAS_STRIPE_SECRET_KEY)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        price_id = request.data.get("priceId") or request.data.get("price_id")
        domain_value = request.data.get("domain")
        if not isinstance(price_id, str) or not price_id:
            return Response({"error": "priceId required"}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(domain_value, str):
            return Response({"error": "domain required for license issuance"}, status=400)
        domain = domain_value.strip()
        if price_id not in _allowed_price_ids():
            return Response({"error": "Unknown or unavailable plan"}, status=status.HTTP_400_BAD_REQUEST)
        if not domain:
            return Response({"error": "domain required for license issuance"}, status=400)

        from apps.licenses.utils import normalize_domain, validate_domain_format

        domain = normalize_domain(domain)
        if not validate_domain_format(domain):
            return Response({"error": "Invalid domain format"}, status=400)

        app_url = getattr(settings, "SAAS_BILLING_RETURN_URL", "http://localhost:5173")
        _get_stripe()
        sub = _get_or_create_subscription(request.user)

        session_params: dict = {
            "mode": "subscription",
            "customer_email": request.user.email,
            "client_reference_id": str(request.user.pk),
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": f"{app_url.rstrip('/')}/billing?success=1",
            "cancel_url": f"{app_url.rstrip('/')}/billing?canceled=1",
            "metadata": {"user_id": str(request.user.pk), "domain": domain},
            "subscription_data": {"metadata": {"user_id": str(request.user.pk), "domain": domain}},
        }
        if sub.stripe_customer_id:
            session_params["customer"] = sub.stripe_customer_id
            del session_params["customer_email"]

        session = stripe.checkout.Session.create(**session_params)
        return Response({"url": session.url})


class PortalView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        if not _stripe_configured():
            return Response(
                {"error": "Platform billing is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        sub = _get_or_create_subscription(request.user)
        if not sub.stripe_customer_id:
            return Response({"error": "No billing account yet — subscribe first."}, status=status.HTTP_400_BAD_REQUEST)

        app_url = getattr(settings, "SAAS_BILLING_RETURN_URL", "http://localhost:5173")
        _get_stripe()
        session = stripe.billingPortal.Session.create(
            customer=sub.stripe_customer_id,
            return_url=f"{app_url.rstrip('/')}/billing",
        )
        return Response({"url": session.url})
