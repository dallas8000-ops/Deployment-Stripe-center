"""Allowed portfolio apps — stored only on this machine (~/.stripe-installer/)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .portfolio_paths import portfolio_data_dir, portfolio_registry_path

EXAMPLE_REGISTRY: dict[str, Any] = {
    "version": 1,
    "allowedApps": [
        {
            "id": "automation-center",
            "name": "Deployment & Stripe Automation Center",
            "productionUrl": "https://stripe-installer-production.up.railway.app",
            "webhookPath": "/api/v1/billing/webhook/",
            "healthPath": "/health/",
            "projectSlug": "stripe-installer",
            "localPath": r"C:\Software Projects\Deployment-Stripe-center",
            "transferAllowedTo": [],
            "notes": "Unified Automation Center. Portfolio live demo: FrontlineDigital portfolioLiveUrls.stripeInstaller",
        },
        {
            "id": "api-transfer-legacy",
            "name": "API Transfer (legacy — retire after cutover)",
            "productionUrl": "https://api-transfer-production.up.railway.app",
            "webhookPath": "/api/billing/webhook",
            "healthPath": "/health/",
            "projectSlug": "api-transfer",
            "transferAllowedTo": [],
            "notes": "Remove this entry after docs/CUTOVER.md checklist is complete.",
        },
    ],
}


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
        return {
            "id": self.id,
            "name": self.name,
            "productionUrl": self.production_url,
            "webhookPath": self.webhook_path,
            "healthPath": self.health_path,
            "projectSlug": self.project_slug,
            "localPath": self.local_path,
            "transferAllowedTo": list(self.transfer_allowed_to),
        }


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
    )


def ensure_registry_template() -> Path:
    path = portfolio_registry_path()
    if path.is_file():
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
