"""Build Jinja2 context from Stripe manifest."""

from __future__ import annotations

import re
from typing import Any


def tier_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def format_amount(cents: int, currency: str) -> str:
    if currency.lower() == "usd":
        return f"${cents / 100:.2f}"
    return f"{cents / 100:.2f} {currency.upper()}"


def tier_cards_from_manifest(manifest: dict | None) -> list[dict[str, Any]]:
    if not manifest:
        return []
    cards = []
    for price in manifest.get("prices", []):
        interval = price.get("interval")
        label = format_amount(price["amount"], price.get("currency", "usd"))
        if interval:
            label = f"{label}/{interval}"
        cards.append(
            {
                "key": tier_key(price["tier"]),
                "tier": price["tier"],
                "price_id": price["id"],
                "label": label,
                "trialDays": price.get("trialDays") or 0,
                "features": price.get("features") or [],
            }
        )
    return cards


def build_context(
    *,
    framework: str,
    manifest: dict | None = None,
    app_url: str = "http://localhost:8000",
    next_router: str | None = None,
) -> dict[str, Any]:
    tiers = tier_cards_from_manifest(manifest)
    price_comments = []
    if manifest:
        for p in manifest.get("prices", []):
            price_comments.append(f"# {p['tier']}: {p['id']}")

    return {
        "framework": framework,
        "manifest": manifest or {},
        "tiers": tiers,
        "price_comments": price_comments,
        "price_comment_block": "\n".join(price_comments) or "# Run stripe-installer run --provision first",
        "app_url": app_url,
        "next_router": next_router or "app",
        "use_app_router": next_router != "pages",
        "webhook_path": _webhook_path(framework),
    }


def _webhook_path(framework: str) -> str:
    if framework in ("nextjs", "remix", "nuxt", "sveltekit"):
        return "/api/stripe/webhook"
    return "/stripe/webhook"


def lib_dir(framework: str) -> str:
    if framework in ("nextjs", "remix"):
        return "lib"
    if framework in ("nuxt", "sveltekit"):
        return "lib"
    return "src/lib"
