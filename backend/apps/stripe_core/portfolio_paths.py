"""Local-only paths for portfolio registry and audit reports (never in git)."""

from __future__ import annotations

import os
from pathlib import Path


def portfolio_data_dir() -> Path:
    raw = os.environ.get("STRIPE_INSTALLER_DATA_DIR", "").strip()
    base = Path(raw).expanduser() if raw else Path.home() / ".stripe-installer"
    base.mkdir(parents=True, exist_ok=True)
    return base


def portfolio_registry_path() -> Path:
    return portfolio_data_dir() / "portfolio-registry.json"


def portfolio_reports_dir() -> Path:
    path = portfolio_data_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path
