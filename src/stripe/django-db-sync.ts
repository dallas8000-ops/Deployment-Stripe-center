/** Python DB + webhook sync for generated Django billing apps. */

export function generateDjangoDbModule(): string {
  return `"""Stripe ↔ PostgreSQL sync (Django database backend).

Requires db/schema.sql applied and DATABASES configured for PostgreSQL.
Deterministic customer lookup: auth_user_id stores Django User.pk as text.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from django.db import connection, transaction


def _cursor():
    return connection.cursor()


def link_customer_from_checkout(session: dict) -> None:
    customer_id = session.get("customer")
    if not customer_id:
        return
    email = session.get("customer_email") or (session.get("customer_details") or {}).get("email")
    user_ref = session.get("client_reference_id") or (session.get("metadata") or {}).get("userId")

    with transaction.atomic():
        with _cursor() as cur:
            if user_ref:
                cur.execute(
                    """
                    INSERT INTO stripe_customers (stripe_customer_id, email, auth_user_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (stripe_customer_id) DO UPDATE SET
                      email = COALESCE(EXCLUDED.email, stripe_customers.email),
                      auth_user_id = COALESCE(EXCLUDED.auth_user_id, stripe_customers.auth_user_id)
                    """,
                    [customer_id, email, str(user_ref)],
                )
            else:
                cur.execute(
                    """
                    INSERT INTO stripe_customers (stripe_customer_id, email)
                    VALUES (%s, %s)
                    ON CONFLICT (stripe_customer_id) DO UPDATE SET
                      email = COALESCE(EXCLUDED.email, stripe_customers.email)
                    """,
                    [customer_id, email],
                )


def sync_subscription_from_stripe(subscription: dict) -> None:
    customer_id = subscription.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    items = (subscription.get("items") or {}).get("data") or []
    price_id = None
    if items:
        price_id = (items[0].get("price") or {}).get("id")
    tier = (subscription.get("metadata") or {}).get("tier")
    period_end = subscription.get("current_period_end")
    period_dt = (
        datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None
    )

    with transaction.atomic():
        with _cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscriptions (
                  stripe_subscription_id, stripe_customer_id, stripe_price_id,
                  status, tier, current_period_end, cancel_at_period_end, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (stripe_subscription_id) DO UPDATE SET
                  stripe_customer_id = EXCLUDED.stripe_customer_id,
                  stripe_price_id = EXCLUDED.stripe_price_id,
                  status = EXCLUDED.status,
                  tier = EXCLUDED.tier,
                  current_period_end = EXCLUDED.current_period_end,
                  cancel_at_period_end = EXCLUDED.cancel_at_period_end,
                  updated_at = NOW()
                """,
                [
                    subscription.get("id"),
                    customer_id,
                    price_id,
                    subscription.get("status"),
                    tier,
                    period_dt,
                    subscription.get("cancel_at_period_end", False),
                ],
            )


def get_stripe_customer_for_user(user_pk) -> str | None:
    """Deterministic lookup for scheduled renewals / billing portal."""
    with _cursor() as cur:
        cur.execute(
            """
            SELECT stripe_customer_id FROM stripe_customers
            WHERE auth_user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [str(user_pk)],
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_active_subscription_for_customer(stripe_customer_id: str) -> dict | None:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT stripe_subscription_id, status, tier, current_period_end
            FROM subscriptions
            WHERE stripe_customer_id = %s AND status IN ('active', 'trialing')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            [stripe_customer_id],
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "subscriptionId": row[0],
            "status": row[1],
            "tier": row[2],
            "currentPeriodEnd": row[3].isoformat() if row[3] else None,
        }


def record_webhook_event(event: dict) -> None:
    with transaction.atomic():
        with _cursor() as cur:
            cur.execute(
                """
                INSERT INTO webhook_events (stripe_event_id, type, payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (stripe_event_id) DO NOTHING
                """,
                [event.get("id"), event.get("type"), json.dumps(event.get("data", {}))],
            )
`;
}

export function generateDjangoWebhookHandlers(): string {
  return `"""Dispatch Stripe webhook events to DB sync handlers."""
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
        # Extend: email ops team or mark subscription past_due in your app
        pass
    elif event_type == "account.updated":
        db.sync_connect_account(data)
    elif event_type in ("transfer.created", "transfer.updated", "transfer.reversed"):
        db.record_transfer(data)
`;
}

export function generateDjangoMeView(): string {
  return `
def stripe_me(request):
    """GET /stripe/me/ — deterministic customer lookup for logged-in users."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"customerId": None, "source": None}, status=401)
    from .db import get_stripe_customer_for_user, get_active_subscription_for_customer

    customer_id = get_stripe_customer_for_user(request.user.pk)
    source = "database" if customer_id else None
    if not customer_id:
        customer_id = request.session.get("stripe_customer_id")
        source = "session" if customer_id else None
    payload = {"customerId": customer_id, "source": source}
    if customer_id:
        sub = get_active_subscription_for_customer(customer_id)
        if sub:
            payload["subscription"] = sub
    return JsonResponse(payload)
`;
}

export function djangoConnectDbExtensions(): string {
  return `

def sync_connect_account(account: dict) -> None:
    stripe_account_id = account.get("id")
    if not stripe_account_id:
        return
    auth_user_id = (account.get("metadata") or {}).get("auth_user_id")
    with transaction.atomic():
        with _cursor() as cur:
            cur.execute(
                """
                INSERT INTO stripe_connect_accounts (
                  stripe_account_id, auth_user_id, charges_enabled, payouts_enabled, details_submitted
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (stripe_account_id) DO UPDATE SET
                  charges_enabled = EXCLUDED.charges_enabled,
                  payouts_enabled = EXCLUDED.payouts_enabled,
                  details_submitted = EXCLUDED.details_submitted,
                  auth_user_id = COALESCE(EXCLUDED.auth_user_id, stripe_connect_accounts.auth_user_id),
                  updated_at = NOW()
                """,
                [
                    stripe_account_id,
                    auth_user_id,
                    account.get("charges_enabled", False),
                    account.get("payouts_enabled", False),
                    account.get("details_submitted", False),
                ],
            )


def get_connect_account_for_user(user_pk) -> str | None:
    with _cursor() as cur:
        cur.execute(
            """
            SELECT stripe_account_id FROM stripe_connect_accounts
            WHERE auth_user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [str(user_pk)],
        )
        row = cur.fetchone()
        return row[0] if row else None


def record_transfer(transfer: dict) -> None:
    with transaction.atomic():
        with _cursor() as cur:
            cur.execute(
                """
                INSERT INTO stripe_transfers (
                  stripe_transfer_id, stripe_account_id, amount, currency, status
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (stripe_transfer_id) DO UPDATE SET
                  status = EXCLUDED.status,
                  updated_at = NOW()
                """,
                [
                    transfer.get("id"),
                    transfer.get("destination"),
                    transfer.get("amount"),
                    transfer.get("currency", "usd"),
                    transfer.get("status") or "created",
                ],
            )
`;
}
