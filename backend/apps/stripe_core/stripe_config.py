"""Read/write stripe.config.json in client project repos."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from apps.stripe_core.provision import DEFAULT_TIERS

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


def _amount_from_price(value: str) -> tuple[int, str] | None:
    text = value.lower().strip()
    if "custom" in text or "contact" in text or "call" in text:
        return None
    match = re.search(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", text)
    if not match:
        return None
    amount = int(round(float(match.group(1).replace(",", "")) * 100))
    interval = "year" if re.search(r"\b(yr|year|annual|annually)\b", text) else "month"
    return amount, interval


def tiers_from_readme(root: Path) -> list[dict[str, Any]]:
    for filename in ("README.md", "readme.md", "Readme.md"):
        path = root / filename
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        tiers: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            if all(set(cell) <= {"-", ":", " "} for cell in cells):
                continue
            name, price = cells[0], cells[1]
            if name.lower() in {"tier", "plan", "name"} or price.lower() in {"price", "pricing"}:
                continue
            parsed = _amount_from_price(price)
            if not parsed:
                continue
            amount, interval = parsed
            tier: dict[str, Any] = {
                "name": name,
                "amount": amount,
                "currency": "usd",
                "interval": interval,
                "trialDays": 0,
            }
            if len(cells) > 2 and cells[2]:
                tier["features"] = [part.strip(" +") for part in re.split(r",|;", cells[2]) if part.strip(" +")]
            tiers.append(tier)
        if tiers:
            return tiers
    return []


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
    readme_tiers = tiers_from_readme(root)
    if readme_tiers:
        return normalize_stripe_config({"tiers": readme_tiers})
    return normalize_stripe_config({})


def provision_config_from_stripe_file(root: Path, *, app_url: str, webhook_path: str) -> dict[str, Any]:
    """Build kwargs for ProvisionConfig from stripe.config.json."""
    from urllib.parse import urlparse

    cfg = config_from_disk(root)
    prov = cfg.get("provision") or {}
    # Caller-supplied app_url wins when it's a real production URL; only fall back to
    # config file's appUrl when the caller didn't provide one (or provided localhost).
    from .provision import _is_public_url

    cfg_url = cfg.get("appUrl") or ""
    if app_url and _is_public_url(app_url):
        url = app_url
    elif cfg_url and _is_public_url(cfg_url):
        url = cfg_url
    else:
        url = app_url or cfg_url or DEFAULT_CONFIG["appUrl"]

    computed_webhook = f"{url.rstrip('/')}{webhook_path}"
    cfg_wh = str(cfg.get("webhookUrl") or "").strip()
    if cfg_wh:
        cfg_host = urlparse(cfg_wh).netloc
        url_host = urlparse(url).netloc
        webhook_url = cfg_wh if (not url_host or not cfg_host or cfg_host == url_host) else computed_webhook
    else:
        webhook_url = computed_webhook

    return {
        "tiers": cfg.get("tiers"),
        "app_url": url,
        "webhook_url": webhook_url,
        "billing_portal_return_url": cfg.get("billingPortalReturnUrl")
        or f"{url.rstrip('/')}/stripe/account/",
        "reuse_existing": prov.get("reuseExisting", True),
        "create_webhook": prov.get("createWebhook", True),
        "create_portal": prov.get("createPortal", True),
    }
