"""Stripe platform billing webhooks — idempotent, org + user subscriptions."""

from __future__ import annotations

import json
import logging

import stripe
from django.conf import settings
from django.db import IntegrityError
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.billing.models import BillingWebhookEvent, OrgSubscription, Subscription

logger = logging.getLogger(__name__)


def _get_stripe():
    stripe.api_key = settings.SAAS_STRIPE_SECRET_KEY
    stripe.api_version = settings.STRIPE_API_VERSION
    return stripe


def _sync_org_subscription(org_id: str, stripe_sub: dict) -> None:
    from apps.organizations.models import Organization

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return

    sub, _ = OrgSubscription.objects.get_or_create(organization=org)
    sub.stripe_subscription_id = stripe_sub.get("id", "") or sub.stripe_subscription_id
    customer = stripe_sub.get("customer")
    if customer:
        sub.stripe_customer_id = customer if isinstance(customer, str) else str(customer)
    sub.status = stripe_sub.get("status", Subscription.Status.NONE)
    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)

    items = (stripe_sub.get("items") or {}).get("data") or []
    if items:
        price = items[0].get("price") or {}
        sub.stripe_price_id = price.get("id", "") or sub.stripe_price_id
        sub.tier = (price.get("metadata") or {}).get("tier") or price.get("nickname") or sub.tier

    period_end = stripe_sub.get("current_period_end")
    if period_end:
        from datetime import datetime, timezone

        sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
    sub.save()


def _sync_subscription(user_id: str, stripe_sub: dict) -> None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return

    sub, _ = Subscription.objects.get_or_create(user=user)
    sub.stripe_subscription_id = stripe_sub.get("id", "") or sub.stripe_subscription_id
    customer = stripe_sub.get("customer")
    if customer:
        sub.stripe_customer_id = customer if isinstance(customer, str) else str(customer)
    sub.status = stripe_sub.get("status", Subscription.Status.NONE)
    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)

    items = (stripe_sub.get("items") or {}).get("data") or []
    if items:
        price = items[0].get("price") or {}
        sub.stripe_price_id = price.get("id", "") or sub.stripe_price_id
        sub.tier = (price.get("metadata") or {}).get("tier") or price.get("nickname") or sub.tier

    period_end = stripe_sub.get("current_period_end")
    if period_end:
        from datetime import datetime, timezone

        sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
    sub.save()


def _sync_subscription_by_customer(customer_id: str, stripe_sub: dict | None = None, *, status: str | None = None) -> None:
    if not customer_id:
        return
    try:
        org_sub = OrgSubscription.objects.get(stripe_customer_id=customer_id)
        if stripe_sub:
            _sync_org_subscription(str(org_sub.organization_id), stripe_sub)
        elif status:
            org_sub.status = status
            org_sub.save(update_fields=["status", "updated_at"])
        return
    except OrgSubscription.DoesNotExist:
        pass
    try:
        sub = Subscription.objects.get(stripe_customer_id=customer_id)
        if stripe_sub:
            _sync_subscription(str(sub.user_id), stripe_sub)
        elif status:
            sub.status = status
            sub.save(update_fields=["status", "updated_at"])
    except Subscription.DoesNotExist:
        pass


def _handle_checkout_completed(session: dict) -> None:
    _get_stripe()
    meta = session.get("metadata") or {}
    ref = session.get("client_reference_id") or ""
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")

    org_id = meta.get("organization_id")
    if ref.startswith("org:"):
        org_id = org_id or ref.split(":", 1)[1]

    if customer_id:
        if org_id:
            from apps.organizations.models import Organization

            try:
                org = Organization.objects.get(pk=org_id)
                sub, _ = OrgSubscription.objects.get_or_create(organization=org)
                sub.stripe_customer_id = customer_id if isinstance(customer_id, str) else str(customer_id)
                sub.save(update_fields=["stripe_customer_id", "updated_at"])
            except Organization.DoesNotExist:
                pass
        else:
            user_id = meta.get("user_id") or (ref if ref and not ref.startswith("org:") else None)
            if user_id:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                try:
                    user = User.objects.get(pk=user_id)
                    sub, _ = Subscription.objects.get_or_create(user=user)
                    sub.stripe_customer_id = customer_id if isinstance(customer_id, str) else str(customer_id)
                    sub.save(update_fields=["stripe_customer_id", "updated_at"])
                except User.DoesNotExist:
                    pass

    if subscription_id:
        stripe_sub = stripe.Subscription.retrieve(subscription_id)
        sub_meta = stripe_sub.get("metadata") or {}
        oid = sub_meta.get("organization_id") or org_id
        uid = sub_meta.get("user_id")
        if oid:
            _sync_org_subscription(str(oid), stripe_sub)
        elif uid:
            _sync_subscription(str(uid), stripe_sub)
        elif customer_id:
            _sync_subscription_by_customer(
                customer_id if isinstance(customer_id, str) else str(customer_id),
                stripe_sub,
            )


def _handle_subscription_event(stripe_sub: dict) -> None:
    meta = stripe_sub.get("metadata") or {}
    org_id = meta.get("organization_id")
    user_id = meta.get("user_id")
    if org_id:
        _sync_org_subscription(str(org_id), stripe_sub)
    elif user_id:
        _sync_subscription(str(user_id), stripe_sub)
    else:
        customer_id = stripe_sub.get("customer")
        if customer_id:
            _sync_subscription_by_customer(
                customer_id if isinstance(customer_id, str) else str(customer_id),
                stripe_sub,
            )


def _handle_invoice_payment_failed(invoice: dict) -> None:
    customer_id = invoice.get("customer")
    if customer_id:
        _sync_subscription_by_customer(
            customer_id if isinstance(customer_id, str) else str(customer_id),
            status=Subscription.Status.PAST_DUE,
        )


def process_billing_event(event: dict) -> None:
    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data)
        # Also trigger license issuance
        try:
            from apps.licenses.webhooks import handle_checkout_session_completed

            handle_checkout_session_completed(data)
        except ImportError:
            logger.debug("License webhook not available")
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        _handle_subscription_event(data)
        # Handle license revocation on subscription deletion
        if event_type == "customer.subscription.deleted":
            try:
                from apps.licenses.webhooks import handle_subscription_deleted

                handle_subscription_deleted(data)
            except ImportError:
                logger.debug("License webhook not available")
    elif event_type == "invoice.payment_failed":
        _handle_invoice_payment_failed(data)
    elif event_type == "invoice.paid":
        subscription_id = data.get("subscription")
        if subscription_id:
            stripe_sub = _get_stripe().Subscription.retrieve(subscription_id)
            _handle_subscription_event(stripe_sub)
    else:
        logger.debug("Unhandled billing webhook event: %s", event_type)


@csrf_exempt
def billing_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    secret = getattr(settings, "SAAS_STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return HttpResponse("Webhook secret not configured", status=400)

    payload = request.body
    sig = request.META.get("HTTP_STRIPE_SIGNATURE")
    _get_stripe()
    try:
        stripe.Webhook.construct_event(payload, sig, secret)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse("Invalid payload", status=400)

    # Use verified JSON payload — Stripe Event objects do not support dict .get().
    try:
        event_payload = json.loads(payload)
    except json.JSONDecodeError:
        return HttpResponse("Invalid payload", status=400)

    event_id = str(event_payload.get("id") or "")
    event_type = str(event_payload.get("type") or "")
    if not event_id:
        return HttpResponse("Missing event id", status=400)

    if BillingWebhookEvent.objects.filter(stripe_event_id=event_id).exists():
        return HttpResponse(json.dumps({"received": True, "duplicate": True}), content_type="application/json")

    try:
        BillingWebhookEvent.objects.create(stripe_event_id=event_id, event_type=event_type)
    except IntegrityError:
        return HttpResponse(json.dumps({"received": True, "duplicate": True}), content_type="application/json")

    try:
        process_billing_event(event_payload)
    except Exception:
        logger.exception("Billing webhook handler failed for %s", event_id)
        BillingWebhookEvent.objects.filter(stripe_event_id=event_id).delete()
        return HttpResponse("Handler error", status=500)

    return HttpResponse(json.dumps({"received": True}), content_type="application/json")
