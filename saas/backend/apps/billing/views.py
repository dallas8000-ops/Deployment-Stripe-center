"""Platform billing — Stripe Installer SaaS subscriptions (dogfooding our own output)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Subscription


def _stripe_configured() -> bool:
    return bool(getattr(settings, "SAAS_STRIPE_SECRET_KEY", ""))


def _get_stripe():
    stripe.api_key = settings.SAAS_STRIPE_SECRET_KEY
    return stripe


def _plans() -> list[dict]:
    plans = []
    for tier, price_id, label, amount in (
        ("Starter", getattr(settings, "SAAS_STRIPE_PRICE_STARTER", ""), "Starter", 900),
        ("Pro", getattr(settings, "SAAS_STRIPE_PRICE_PRO", ""), "Pro", 2900),
        ("Enterprise", getattr(settings, "SAAS_STRIPE_PRICE_ENTERPRISE", ""), "Enterprise", 99000),
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


def _get_or_create_subscription(user) -> Subscription:
    sub, _ = Subscription.objects.get_or_create(user=user)
    return sub


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
        if not price_id:
            return Response({"error": "priceId required"}, status=status.HTTP_400_BAD_REQUEST)

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
            "metadata": {"user_id": str(request.user.pk)},
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


def _sync_subscription(user_id: str, stripe_sub: dict) -> None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return

    sub = _get_or_create_subscription(user)
    sub.stripe_subscription_id = stripe_sub.get("id", "")
    sub.stripe_customer_id = stripe_sub.get("customer", sub.stripe_customer_id)
    sub.status = stripe_sub.get("status", Subscription.Status.NONE)
    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)

    items = (stripe_sub.get("items") or {}).get("data") or []
    if items:
        price = items[0].get("price") or {}
        sub.stripe_price_id = price.get("id", "")
        sub.tier = (price.get("metadata") or {}).get("tier") or price.get("nickname") or sub.tier

    period_end = stripe_sub.get("current_period_end")
    if period_end:
        sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
    sub.save()


@csrf_exempt
def billing_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    payload = request.body
    sig = request.META.get("HTTP_STRIPE_SIGNATURE")
    secret = getattr(settings, "SAAS_STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return HttpResponse("Webhook secret not configured", status=400)

    _get_stripe()
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse("Invalid payload", status=400)

    data = event.get("data", {}).get("object", {})
    event_type = event.get("type")

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id") or (data.get("metadata") or {}).get("user_id")
        customer_id = data.get("customer")
        if user_id and customer_id:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            try:
                user = User.objects.get(pk=user_id)
                sub = _get_or_create_subscription(user)
                sub.stripe_customer_id = customer_id if isinstance(customer_id, str) else customer_id
                sub.save(update_fields=["stripe_customer_id", "updated_at"])
            except User.DoesNotExist:
                pass

    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        user_id = (data.get("metadata") or {}).get("user_id")
        if not user_id:
            customer_id = data.get("customer")
            if customer_id:
                try:
                    sub = Subscription.objects.get(stripe_customer_id=customer_id)
                    user_id = str(sub.user_id)
                except Subscription.DoesNotExist:
                    user_id = None
        if user_id:
            _sync_subscription(user_id, data)

    return HttpResponse(json.dumps({"received": True}), content_type="application/json")
