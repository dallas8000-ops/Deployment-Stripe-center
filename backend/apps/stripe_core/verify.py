"""Stripe API key verification — port of src/stripe/stripe-client.ts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import stripe

Mode = Literal["test", "live", "unknown"]


@dataclass
class KeyCheck:
    valid: bool
    mode: Mode
    message: str


@dataclass
class VerificationResult:
    secret_key: KeyCheck
    publishable_key: KeyCheck
    account_id: str | None = None
    account_name: str | None = None
    country: str | None = None
    billing_enabled: bool | None = None

    def to_public_dict(self) -> dict:
        return {
            "secretKey": {
                "valid": self.secret_key.valid,
                "mode": self.secret_key.mode,
                "message": self.secret_key.message,
            },
            "publishableKey": {
                "valid": self.publishable_key.valid,
                "mode": self.publishable_key.mode,
                "message": self.publishable_key.message,
            },
            "accountId": self.account_id,
            "accountName": self.account_name,
            "country": self.country,
            "billingEnabled": self.billing_enabled,
        }


def _detect_mode(key: str) -> Mode:
    if "_test_" in key:
        return "test"
    if "_live_" in key:
        return "live"
    return "unknown"


def verify_stripe_keys(secret_key: str | None, publishable_key: str | None) -> VerificationResult:
    result = VerificationResult(
        secret_key=KeyCheck(False, _detect_mode(secret_key or ""), "Not configured"),
        publishable_key=KeyCheck(False, _detect_mode(publishable_key or ""), "Not configured"),
    )

    if not secret_key:
        result.secret_key.message = "STRIPE_SECRET_KEY missing from vault"
        return result

    if not re.match(r"^sk_(test|live)_", secret_key):
        result.secret_key.message = "Invalid secret key format (expected sk_test_ or sk_live_)"
        return result

    try:
        stripe.api_key = secret_key
        Balance = stripe.Balance
        Account = stripe.Account
        Balance.retrieve()
        account = Account.retrieve()
        result.secret_key.valid = True
        result.secret_key.message = f"Valid ({result.secret_key.mode} mode, balance available)"
        result.account_id = account.id
        bp = getattr(account, "business_profile", None)
        settings = getattr(account, "settings", None)
        dashboard = getattr(settings, "dashboard", None) if settings else None
        result.account_name = (
            (getattr(bp, "name", None) if bp else None)
            or (getattr(dashboard, "display_name", None) if dashboard else None)
            or account.id
        )
        result.country = getattr(account, "country", None)
        caps = getattr(account, "capabilities", None)
        result.billing_enabled = getattr(caps, "card_payments", None) == "active" if caps else None
    except stripe.StripeError as exc:
        result.secret_key.message = str(getattr(exc, "user_message", None) or exc)
    except Exception as exc:
        result.secret_key.message = f"Verification failed: {exc}"

    if not publishable_key:
        result.publishable_key.message = "STRIPE_PUBLISHABLE_KEY missing from vault"
        return result

    if not re.match(r"^pk_(test|live)_", publishable_key):
        result.publishable_key.message = "Invalid publishable key format (expected pk_test_ or pk_live_)"
        return result

    if (
        result.secret_key.valid
        and result.secret_key.mode != "unknown"
        and result.publishable_key.mode != "unknown"
        and result.secret_key.mode != result.publishable_key.mode
    ):
        result.publishable_key.message = (
            f"Mode mismatch: secret is {result.secret_key.mode}, "
            f"publishable is {result.publishable_key.mode}"
        )
        return result

    result.publishable_key.valid = True
    result.publishable_key.message = f"Valid ({result.publishable_key.mode} mode)"
    return result
