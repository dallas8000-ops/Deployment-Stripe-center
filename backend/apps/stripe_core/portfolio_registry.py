"""Allowed portfolio apps — stored only on this machine (~/.stripe-installer/).

A checked-in seed (apps/stripe_core/data/portfolio-registry.seed.json) is used to
populate the first-run template so localPath survives Railway wiping
~/.stripe-installer/ on redeploy. See ensure_registry_template().
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .portfolio_paths import portfolio_data_dir, portfolio_registry_path

EXAMPLE_REGISTRY: dict[str, Any] = {
    "version": 1,
    "allowedApps": [],
}

# Checked into git — the source of truth for first-run / post-redeploy seeding.
SEED_REGISTRY_PATH = Path(__file__).resolve().parent / "data" / "portfolio-registry.seed.json"


def _example_apps_from_catalog() -> list[dict[str, Any]]:
    from .portfolio_catalog import PORTFOLIO_CATALOG

    apps: list[dict[str, Any]] = []
    for entry in PORTFOLIO_CATALOG:
        if entry.get("merged"):
            continue
        apps.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "productionUrl": entry.get("productionUrl", ""),
                "webhookPath": entry.get("webhookPath", "/stripe/webhook"),
                "healthPath": entry.get("healthPath", "/health/"),
                "projectSlug": entry.get("projectSlug", ""),
                "localPath": entry.get("defaultLocalPath", ""),
                "transferAllowedTo": [],
                "stripeExempt": bool(entry.get("stripeExempt")),
                "notes": entry.get("notes", ""),
            }
        )
    return apps


EXAMPLE_REGISTRY["allowedApps"] = _example_apps_from_catalog()


@dataclass
class PortfolioApp:
    id: str
    name: str
    production_url: str = ""
    webhook_path: str = "/stripe/webhook"
    health_path: str = "/health/"
    project_slug: str = ""
    local_path: str = ""
    transfer_allowed_to: list[str] = field(default_factory=list)
    stripe_exempt: bool = False
    notes: str = ""

    @property
    def requires_stripe_webhook(self) -> bool:
        return not self.stripe_exempt and bool(self.production_url) and bool(self.webhook_path)

    @property
    def webhook_url(self) -> str:
        base = self.production_url.rstrip("/")
        path = self.webhook_path if self.webhook_path.startswith("/") else f"/{self.webhook_path}"
        return f"{base}{path}" if base else ""

    @property
    def health_url(self) -> str:
        base = self.production_url.rstrip("/")
        path = self.health_path if self.health_path.startswith("/") else f"/{self.health_path}"
        return f"{base}{path}" if base else ""

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "name": self.name,
            "productionUrl": self.production_url,
            "webhookPath": self.webhook_path,
            "healthPath": self.health_path,
            "projectSlug": self.project_slug,
            "localPath": self.local_path,
            "transferAllowedTo": list(self.transfer_allowed_to),
        }
        if self.stripe_exempt:
            data["stripeExempt"] = True
        if self.notes:
            data["notes"] = self.notes
        return data


def _parse_app(raw: dict[str, Any]) -> PortfolioApp:
    return PortfolioApp(
        id=str(raw.get("id") or "").strip(),
        name=str(raw.get("name") or raw.get("id") or "").strip(),
        production_url=str(raw.get("productionUrl") or "").strip().rstrip("/"),
        webhook_path=str(raw.get("webhookPath") or "/stripe/webhook").strip(),
        health_path=str(raw.get("healthPath") or "/health/").strip(),
        project_slug=str(raw.get("projectSlug") or "").strip(),
        local_path=str(raw.get("localPath") or "").strip(),
        transfer_allowed_to=[
            str(x).strip() for x in (raw.get("transferAllowedTo") or []) if str(x).strip()
        ],
        stripe_exempt=bool(raw.get("stripeExempt")),
        notes=str(raw.get("notes") or "").strip(),
    )


def ensure_registry_template() -> Path:
    path = portfolio_registry_path()
    if path.is_file():
        return path

    # Prefer the checked-in seed (real localPath values, reviewed in git) over the
    # catalog-derived template. This is what makes the registry survive Railway
    # wiping ~/.stripe-installer/ on every redeploy: the seed always exists.
    if SEED_REGISTRY_PATH.is_file():
        seed_text = SEED_REGISTRY_PATH.read_text(encoding="utf-8")
        path.write_text(seed_text, encoding="utf-8")
        example = portfolio_data_dir() / "portfolio-registry.example.json"
        example.write_text(seed_text, encoding="utf-8")
        return path

    example = portfolio_data_dir() / "portfolio-registry.example.json"
    example.write_text(json.dumps(EXAMPLE_REGISTRY, indent=2) + "\n", encoding="utf-8")
    path.write_text(json.dumps(EXAMPLE_REGISTRY, indent=2) + "\n", encoding="utf-8")
    return path


def load_registry() -> list[PortfolioApp]:
    path = ensure_registry_template()
    raw = json.loads(path.read_text(encoding="utf-8"))
    apps = raw.get("allowedApps") or []
    if not isinstance(apps, list):
        raise ValueError("portfolio-registry.json: allowedApps must be a list")
    parsed = [_parse_app(entry) for entry in apps if isinstance(entry, dict) and entry.get("id")]
    return parsed


def save_registry(apps: list[PortfolioApp]) -> Path:
    path = portfolio_registry_path()
    payload = {
        "version": 1,
        "allowedApps": [app.to_dict() for app in apps],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def find_app_by_webhook_url(url: str, apps: list[PortfolioApp]) -> PortfolioApp | None:
    normalized = url.rstrip("/")
    for app in apps:
        if app.webhook_url.rstrip("/") == normalized:
            return app
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    for app in apps:
        if not app.production_url:
            continue
        app_host = (urlparse(app.production_url).hostname or "").lower()
        app_path = app.webhook_path.rstrip("/")
        req_path = (parsed.path or "").rstrip("/")
        if host == app_host and req_path == app_path:
            return app
    return None


def transfer_permitted(source_id: str, target_id: str, apps: list[PortfolioApp]) -> bool:
    source = next((a for a in apps if a.id == source_id), None)
    if not source:
        return False
    return target_id in source.transfer_allowed_to
