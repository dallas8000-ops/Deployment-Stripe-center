"""Shared license validation for middleware, startup, and health checks."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)

_validator = None
_validator_lock = threading.Lock()
_last_valid: bool | None = None
_last_checked: datetime | None = None


def license_enforcement_enabled() -> bool:
    return getattr(settings, "LICENSE_ENFORCEMENT_ENABLED", False)


def license_configured() -> bool:
    return bool(os.environ.get("STRIPE_INSTALLER_LICENSE_KEY") and os.environ.get("STRIPE_INSTALLER_DOMAIN"))


def get_validator():
    """Lazy singleton LicenseValidator from environment."""
    global _validator
    if _validator is not None:
        return _validator
    with _validator_lock:
        if _validator is not None:
            return _validator
        from apps.licenses.client_validation import LicenseValidator

        key = os.environ.get("STRIPE_INSTALLER_LICENSE_KEY", "")
        domain = os.environ.get("STRIPE_INSTALLER_DOMAIN", "")
        server = os.environ.get(
            "STRIPE_INSTALLER_VALIDATION_SERVER",
            getattr(settings, "APP_PUBLIC_URL", "") or "http://127.0.0.1:8000",
        )
        if not key or not domain:
            return None
        _validator = LicenseValidator(license_key=key, domain=domain, validation_server=server)
        return _validator


def check_license_valid(*, force: bool = False) -> bool:
    """Return True if license is valid or enforcement is disabled."""
    global _last_valid, _last_checked

    if not license_enforcement_enabled():
        return True

    if not license_configured():
        logger.warning("License enforcement enabled but STRIPE_INSTALLER_LICENSE_KEY/DOMAIN not set")
        return False

    validator = get_validator()
    if not validator:
        return False

    if not force and _last_checked and _last_valid is not None:
        hours = (datetime.now(timezone.utc) - _last_checked).total_seconds() / 3600
        if hours < 1:
            return _last_valid

    valid = validator.validate(force=force)
    _last_valid = valid
    _last_checked = datetime.now(timezone.utc)
    return valid


def license_status() -> dict:
    """Status for health endpoint and setup command."""
    enforced = license_enforcement_enabled()
    configured = license_configured()
    if not enforced:
        return {
            "enforcement": "disabled",
            "configured": configured,
            "valid": True,
            "message": "License enforcement off (dev mode)",
        }
    if not configured:
        return {
            "enforcement": "enabled",
            "configured": False,
            "valid": False,
            "message": "Set STRIPE_INSTALLER_LICENSE_KEY and STRIPE_INSTALLER_DOMAIN",
        }
    valid = check_license_valid()
    status = get_validator().get_validation_status() if get_validator() else {}
    return {
        "enforcement": "enabled",
        "configured": True,
        "valid": valid,
        "domain": os.environ.get("STRIPE_INSTALLER_DOMAIN"),
        "lastValidated": status.get("last_validated"),
        "expiryDate": status.get("expiry_date"),
        "message": status.get("message"),
    }
