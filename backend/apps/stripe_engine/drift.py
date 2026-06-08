"""Detect drift between repo manifest and Stripe Dashboard."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import stripe

from apps.deploy.postgres import get_production_url
from apps.projects.models import Project
from apps.stripe_engine.pipeline import _webhook_path
from apps.stripe_engine.provision import INSTALLER_TAG, load_manifest
from apps.vault.models import get_secret


@dataclass
class DriftItem:
    category: str
    severity: str
    message: str
    fix: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_drift(project: Project) -> dict[str, Any]:
    secret = get_secret(project, "STRIPE_SECRET_KEY")
    if not secret:
        raise RuntimeError("STRIPE_SECRET_KEY not in vault")

    root = Path(project.local_path).resolve() if project.local_path else None
    manifest = load_manifest(root) if root and root.is_dir() else None
    items: list[DriftItem] = []

    stripe.api_key = secret
    expected_url = get_production_url(project, "")
    if expected_url:
        webhook_path = _webhook_path(project.framework or "unknown")
        expected_webhook = f"{expected_url.rstrip('/')}{webhook_path}"
        endpoints = stripe.WebhookEndpoint.list(limit=20)
        matching = [ep for ep in endpoints.data if ep.url == expected_webhook]
        if not matching:
            items.append(
                DriftItem(
                    "webhook",
                    "warning",
                    f"No Stripe webhook registered for {expected_webhook}",
                    "Run deploy prep or fix → provision-stripe after setting production URL",
                )
            )
        else:
            for ep in endpoints.data:
                if ep.url != expected_webhook and INSTALLER_TAG in (ep.metadata or {}):
                    items.append(
                        DriftItem(
                            "webhook",
                            "warning",
                            f"Stale webhook URL in Stripe: {ep.url}",
                            f"Update or delete endpoint; expected {expected_webhook}",
                        )
                    )

    manifest_prices = (manifest or {}).get("prices") or []
    if manifest_prices:
        live_prices = stripe.Price.list(limit=100, active=True)
        live_by_id = {p.id: p for p in live_prices.data}
        for entry in manifest_prices:
            pid = entry.get("id") if isinstance(entry, dict) else None
            if not pid:
                continue
            live = live_by_id.get(pid)
            if not live:
                items.append(
                    DriftItem(
                        "catalog",
                        "error",
                        f"Manifest price {pid} not found in Stripe",
                        "Re-run provision or update stripe-manifest.json",
                    )
                )
            elif isinstance(entry, dict) and entry.get("unit_amount") is not None:
                if live.unit_amount != entry.get("unit_amount"):
                    items.append(
                        DriftItem(
                            "catalog",
                            "warning",
                            f"Price {pid} amount drift: manifest {entry.get('unit_amount')} vs Stripe {live.unit_amount}",
                            "Align Stripe Dashboard or re-provision from stripe.config.json",
                        )
                    )

    scan = project.scan_data or {}
    stored_url = scan.get("productionUrl") or ""
    if stored_url and expected_url and stored_url.rstrip("/") != expected_url.rstrip("/"):
        items.append(
            DriftItem(
                "config",
                "info",
                f"productionUrl mismatch: scan_data vs deploy.config",
                "Sync project Settings and deploy.config.json",
            )
        )

    from datetime import datetime, timezone

    return {
        "driftCount": len(items),
        "items": [i.to_dict() for i in items],
        "manifestPriceCount": len(manifest_prices),
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


def persist_drift_snapshot(project: Project, result: dict[str, Any]) -> None:
    scan = dict(project.scan_data or {})
    scan["lastDrift"] = {
        "driftCount": result.get("driftCount", 0),
        "checkedAt": result.get("checkedAt"),
        "manifestPriceCount": result.get("manifestPriceCount", 0),
        "items": (result.get("items") or [])[:25],
    }
    project.scan_data = scan
    project.save(update_fields=["scan_data", "updated_at"])
