"""Tamper-evident audit log for API Transfer operations."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.api_transfer.integrity import integrity_hash
from apps.api_transfer.redaction import redact_sensitive_values

from .models import AuditEntry

VALID_ACTIONS = {
    "plan",
    "apply",
    "rollback",
    "verify",
    "discover",
    "status",
    "env_inject",
    "railway_env_backup",
    "platform_setup",
    "client_prewire",
}


def record_audit(action: str, actor: str, payload: dict[str, Any], reference: str = "") -> dict[str, Any]:
    if action not in VALID_ACTIONS:
        raise ValueError(f"Unknown audit action: {action}")

    safe_payload = redact_sensitive_values(payload)
    with transaction.atomic():
        last = AuditEntry.objects.select_for_update().order_by("-sequence").first()
        sequence = (last.sequence + 1) if last else 1
        previous_hash = last.entry_hash if last else ""
        entry_hash = integrity_hash(
            {
                "sequence": sequence,
                "action": action,
                "actor": actor,
                "reference": reference,
                "payload": safe_payload,
                "previousHash": previous_hash,
            }
        )
        entry = AuditEntry.objects.create(
            sequence=sequence,
            action=action,
            actor=actor,
            reference=reference,
            payload=safe_payload,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )
    return entry.to_dict()
