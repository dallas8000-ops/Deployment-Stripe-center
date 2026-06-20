"""Dispatch Stripe webhook events to DB sync handlers."""
from __future__ import annotations

from . import db


def dispatch_stripe_event(event: dict) -> None:
    db.record_webhook_event(event)
    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        db.link_customer_from_checkout(data)
    elif event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        db.sync_subscription_from_stripe(data)
    elif event_type == "invoice.payment_failed":
        pass
