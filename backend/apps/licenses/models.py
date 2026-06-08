import secrets
from datetime import datetime, timezone

from django.db import models


class License(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    key = models.CharField(max_length=64, unique=True, db_index=True)
    customer_email = models.EmailField()
    stripe_subscription_id = models.CharField(max_length=64, blank=True, db_index=True)
    stripe_customer_id = models.CharField(max_length=64, blank=True, db_index=True)
    registered_domain = models.CharField(max_length=255, db_index=True)
    max_instances = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    expiry_date = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["key", "status"]),
            models.Index(fields=["stripe_subscription_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.key[:8]}... ({self.customer_email})"

    @classmethod
    def generate_key(cls) -> str:
        """Generate a cryptographically secure license key."""
        return secrets.token_urlsafe(48)

    @property
    def is_active(self) -> bool:
        """Check if license is currently active."""
        if self.status != self.Status.ACTIVE:
            return False
        if self.expiry_date and self.expiry_date < datetime.now(timezone.utc):
            return False
        return True

    @property
    def active_instance_count(self) -> int:
        """Count of instances seen within the last 48 hours."""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        return self.instances.filter(last_seen__gte=cutoff).count()

    def can_register_instance(self) -> bool:
        """Check if license can register a new instance."""
        return self.is_active and self.active_instance_count < self.max_instances


class InstanceRegistry(models.Model):
    instance_id = models.CharField(max_length=64, unique=True, db_index=True)
    license = models.ForeignKey(
        License, on_delete=models.CASCADE, related_name="instances", db_index=True
    )
    domain = models.CharField(max_length=255)
    last_seen = models.DateTimeField(auto_now=True)
    first_registered = models.DateTimeField(auto_now_add=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen"]
        indexes = [
            models.Index(fields=["instance_id", "license"]),
            models.Index(fields=["license", "last_seen"]),
        ]

    def __str__(self) -> str:
        return f"{self.instance_id[:8]}... ({self.domain})"

    @property
    def is_active(self) -> bool:
        """Instance is considered active if seen within 48 hours."""
        from datetime import timedelta

        return self.last_seen >= datetime.now(timezone.utc) - timedelta(hours=48)
