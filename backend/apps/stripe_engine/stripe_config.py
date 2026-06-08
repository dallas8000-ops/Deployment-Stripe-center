"""Read/write stripe.config.json in client project repos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps.stripe_engine.provision import DEFAULT_TIERS

DEFAULT_CONFIG: dict[str, Any] = {
    "appUrl": "http://localhost:3000",
    "provision": {
        "reuseExisting": True,
        "createWebhook": True,
        "createPortal": True,
    },
    "tiers": DEFAULT_TIERS,
}


def stripe_config_path(root: Path) -> Path:
    return root / "stripe.config.json"


def read_stripe_config(root: Path) -> dict[str, Any]:
    path = stripe_config_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid stripe.config.json: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("stripe.config.json must be a JSON object")
    return raw


def normalize_stripe_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = {**DEFAULT_CONFIG, **raw}
    if "provision" in raw and isinstance(raw["provision"], dict):
        config["provision"] = {**DEFAULT_CONFIG["provision"], **raw["provision"]}
    tiers = raw.get("tiers")
    if tiers is not None:
        if not isinstance(tiers, list) or not tiers:
            raise ValueError("tiers must be a non-empty list")
        for tier in tiers:
            if not isinstance(tier, dict) or "name" not in tier or "amount" not in tier:
                raise ValueError("Each tier requires name and amount")
    else:
        config["tiers"] = list(DEFAULT_TIERS)
    config["appUrl"] = str(config.get("appUrl") or DEFAULT_CONFIG["appUrl"]).rstrip("/")
    return config


def write_stripe_config(root: Path, config: dict[str, Any]) -> Path:
    normalized = normalize_stripe_config(config)
    path = stripe_config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    return path


def config_from_disk(root: Path) -> dict[str, Any]:
    try:
        on_disk = read_stripe_config(root)
        if on_disk:
            return normalize_stripe_config(on_disk)
    except ValueError:
        pass
    return normalize_stripe_config({})


def provision_config_from_stripe_file(root: Path, *, app_url: str, webhook_path: str) -> dict[str, Any]:
    """Build kwargs for ProvisionConfig from stripe.config.json."""
    cfg = config_from_disk(root)
    prov = cfg.get("provision") or {}
    url = app_url or cfg.get("appUrl") or DEFAULT_CONFIG["appUrl"]
    return {
        "tiers": cfg.get("tiers"),
        "app_url": url,
        "webhook_url": cfg.get("webhookUrl") or f"{url.rstrip('/')}{webhook_path}",
        "billing_portal_return_url": cfg.get("billingPortalReturnUrl")
        or f"{url.rstrip('/')}/stripe/account/",
        "reuse_existing": prov.get("reuseExisting", True),
        "create_webhook": prov.get("createWebhook", True),
        "create_portal": prov.get("createPortal", True),
    }
