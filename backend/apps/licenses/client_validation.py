"""
Client-side license validation module for deployed Stripe Installer instances.

This module should be included in the deployed Stripe Installer codebase.
It handles startup validation and periodic re-validation every 24 hours.
"""

import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class LicenseValidator:
    """
    Validates license keys against the Stripe Installer licensing server.
    
    Usage:
        validator = LicenseValidator(
            license_key="your-license-key",
            domain="your-domain.com",
            validation_server="https://your-server.com"
        )
        
        if validator.validate():
            print("License valid!")
        else:
            print("License invalid!")
    """

    def __init__(
        self,
        license_key: str,
        domain: str,
        validation_server: str = "https://api.stripe-installer.com",
        instance_id: Optional[str] = None,
    ):
        self.license_key = license_key
        from apps.licenses.utils import normalize_domain

        self.domain = normalize_domain(domain)
        self.validation_server = validation_server.rstrip("/")
        self.instance_id = instance_id or self._get_or_create_instance_id()
        self._last_validation: Optional[dict] = None
        self._last_validation_time: Optional[datetime] = None
        self._validation_lock = threading.Lock()
        self._background_thread: Optional[threading.Thread] = None
        self._stop_background = threading.Event()

    def _get_or_create_instance_id(self) -> str:
        """Get or create a persistent instance ID."""
        instance_file = Path.home() / ".stripe-installer-instance-id"
        
        if instance_file.exists():
            try:
                with open(instance_file) as f:
                    return f.read().strip()
            except (IOError, OSError):
                pass
        
        # Generate new instance ID
        instance_id = secrets.token_urlsafe(32)
        try:
            instance_file.parent.mkdir(parents=True, exist_ok=True)
            with open(instance_file, "w") as f:
                f.write(instance_id)
        except (IOError, OSError):
            logger.warning("Could not persist instance ID")
        
        return instance_id

    def validate(self, force: bool = False) -> bool:
        """
        Validate the license.
        
        Args:
            force: Force validation even if recently validated (within 24 hours)
        
        Returns:
            True if license is valid, False otherwise
        """
        # Check if we have a recent valid validation (within 24 hours)
        if not force and self._last_validation_time:
            hours_since_validation = (datetime.now(timezone.utc) - self._last_validation_time).total_seconds() / 3600
            if hours_since_validation < 24 and self._last_validation and self._last_validation.get("valid"):
                logger.debug("Using cached validation result")
                return True

        try:
            response = requests.post(
                f"{self.validation_server}/api/v1/license/validate/",
                json={
                    "license_key": self.license_key,
                    "domain": self.domain,
                    "instance_id": self.instance_id,
                },
                timeout=30,
            )
            response.raise_for_status()
            
            result = response.json()
            is_valid = result.get("valid", False)
            
            with self._validation_lock:
                self._last_validation = result
                self._last_validation_time = datetime.now(timezone.utc)
            
            if is_valid:
                logger.info(f"License validated successfully for {self.domain}")
                expiry = result.get("expiry_date")
                if expiry:
                    logger.info(f"License expires: {expiry}")
            else:
                logger.warning(f"License validation failed: {result.get('message', 'Unknown error')}")
            
            return is_valid
            
        except requests.RequestException as e:
            logger.error(f"License validation request failed: {e}")
            # If we have a recent valid validation, allow grace period
            if self._last_validation_time and self._last_validation and self._last_validation.get("valid"):
                hours_since = (datetime.now(timezone.utc) - self._last_validation_time).total_seconds() / 3600
                if hours_since < 48:  # 48-hour grace period
                    logger.warning("Using cached validation due to network error (grace period)")
                    return True
            return False

    def start_background_validation(self, interval_hours: int = 24):
        """
        Start background thread for periodic validation.
        
        Args:
            interval_hours: Hours between validation checks
        """
        if self._background_thread and self._background_thread.is_alive():
            logger.warning("Background validation already running")
            return

        self._stop_background.clear()
        
        def validation_loop():
            while not self._stop_background.is_set():
                self.validate()
                # Wait for interval or stop signal
                self._stop_background.wait(timeout=interval_hours * 3600)
        
        self._background_thread = threading.Thread(target=validation_loop, daemon=True)
        self._background_thread.start()
        logger.info(f"Background validation started (interval: {interval_hours}h)")

    def stop_background_validation(self):
        """Stop background validation thread."""
        if self._background_thread and self._background_thread.is_alive():
            self._stop_background.set()
            self._background_thread.join(timeout=5)
            logger.info("Background validation stopped")

    def get_validation_status(self) -> dict:
        """Get current validation status."""
        with self._validation_lock:
            return {
                "valid": self._last_validation.get("valid") if self._last_validation else False,
                "last_validated": self._last_validation_time.isoformat() if self._last_validation_time else None,
                "expiry_date": self._last_validation.get("expiry_date") if self._last_validation else None,
                "message": self._last_validation.get("message") if self._last_validation else "Not validated",
            }


def validate_on_startup(
    license_key: Optional[str] = None,
    domain: Optional[str] = None,
    validation_server: Optional[str] = None,
) -> bool:
    """
    Convenience function for startup validation.
    
    Reads configuration from environment variables:
    - STRIPE_INSTALLER_LICENSE_KEY
    - STRIPE_INSTALLER_DOMAIN
    - STRIPE_INSTALLER_VALIDATION_SERVER
    
    Returns:
        True if license is valid, False otherwise
    """
    license_key = license_key or os.environ.get("STRIPE_INSTALLER_LICENSE_KEY")
    domain = domain or os.environ.get("STRIPE_INSTALLER_DOMAIN")
    validation_server = validation_server or os.environ.get(
        "STRIPE_INSTALLER_VALIDATION_SERVER", "https://api.stripe-installer.com"
    )

    if not license_key or not domain:
        logger.error("License key and domain must be provided (via args or env vars)")
        return False

    validator = LicenseValidator(
        license_key=license_key,
        domain=domain,
        validation_server=validation_server,
    )

    if not validator.validate(force=True):
        logger.error("Startup license validation failed")
        return False

    # Start background validation
    validator.start_background_validation(interval_hours=24)

    return True


class LicenseError(Exception):
    """Raised when license validation fails."""

    pass


def require_valid_license(func):
    """
    Decorator to require valid license for function execution.
    
    Usage:
        @require_valid_license
        def protected_function():
            # This will only run if license is valid
            pass
    """
    def wrapper(*args, **kwargs):
        license_key = os.environ.get("STRIPE_INSTALLER_LICENSE_KEY")
        domain = os.environ.get("STRIPE_INSTALLER_DOMAIN")
        
        if not license_key or not domain:
            raise LicenseError("License key and domain must be configured")
        
        validator = LicenseValidator(
            license_key=license_key,
            domain=domain,
            validation_server=os.environ.get(
                "STRIPE_INSTALLER_VALIDATION_SERVER", "https://api.stripe-installer.com"
            ),
        )
        
        if not validator.validate():
            raise LicenseError("License validation failed")
        
        return func(*args, **kwargs)
    
    return wrapper
