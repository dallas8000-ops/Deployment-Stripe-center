"""Verify individual vault keys after save."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.stripe_engine.verify import verify_stripe_keys

if TYPE_CHECKING:
    from apps.projects.models import Project


def verify_vault_key(project: Project, key_name: str) -> tuple[bool, str, str]:
    """
    Returns (verified, message, mode).
    Runs live Stripe API check for secret/publishable keys.
    """
    from apps.vault.models import get_secret

    if key_name == "STRIPE_SECRET_KEY":
        secret = get_secret(project, "STRIPE_SECRET_KEY")
        publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
        result = verify_stripe_keys(secret, publishable)
        if result.secret_key.valid:
            return True, "Verified with Stripe", result.secret_key.mode
        return False, result.secret_key.message, result.secret_key.mode

    if key_name == "STRIPE_PUBLISHABLE_KEY":
        secret = get_secret(project, "STRIPE_SECRET_KEY")
        publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
        result = verify_stripe_keys(secret, publishable)
        if result.publishable_key.valid:
            return True, "Verified with Stripe", result.publishable_key.mode
        return False, result.publishable_key.message, result.publishable_key.mode

    if key_name == "STRIPE_WEBHOOK_SECRET":
        value = get_secret(project, key_name)
        if value and value.startswith("whsec_") and len(value) > 10:
            return True, "Format valid", "unknown"
        return False, "Invalid webhook secret format (expected whsec_…)", "unknown"

    return True, "Stored securely", "unknown"
