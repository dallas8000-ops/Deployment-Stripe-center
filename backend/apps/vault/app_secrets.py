"""Stripe Installer's own secrets — stored only under ~/.stripe-installer/ (never in git)."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from apps.stripe_core.portfolio_paths import portfolio_data_dir

logger = logging.getLogger(__name__)

APP_SECRETS_FILENAME = "app-secrets.env"

# Platform / installer secrets — not per-project portfolio keys.
APP_SECRET_KEYS = frozenset(
    {
        "DJANGO_SECRET_KEY",
        "SAAS_STRIPE_SECRET_KEY",
        "SAAS_STRIPE_WEBHOOK_SECRET",
        "SAAS_STRIPE_PRICE_STARTER",
        "SAAS_STRIPE_PRICE_PRO",
        "SAAS_STRIPE_PRICE_ENTERPRISE",
        "SAAS_BILLING_RETURN_URL",
        "GITHUB_WEBHOOK_SECRET",
        "GITHUB_APP_PRIVATE_KEY",
        "STRIPE_INSTALLER_LICENSE_KEY",
        "STRIPE_INSTALLER_DOMAIN",
        "STRIPE_INSTALLER_VALIDATION_SERVER",
    }
)

ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def app_secrets_path() -> Path:
    return portfolio_data_dir() / APP_SECRETS_FILENAME


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE.match(stripped)
        if not match:
            continue
        key, raw = match.group(1), match.group(2).strip()
        value = raw.strip().strip('"').strip("'")
        if value:
            values[key] = value
    return values


def migrate_app_secrets_from_backend_env(backend_env: Path) -> int:
    """Copy installer secrets from backend/.env into ~/.stripe-installer/app-secrets.env once."""
    target = app_secrets_path()
    if target.is_file():
        return 0
    if not backend_env.is_file():
        return 0

    source = parse_env_file(backend_env)
    to_write = {k: v for k, v in source.items() if k in APP_SECRET_KEYS}
    if not to_write:
        return 0

    lines = [f"{k}={v}" for k, v in sorted(to_write.items())]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    logger.info("Migrated %s installer secret(s) to %s", len(to_write), target)
    return len(to_write)


def load_app_secrets_into_environ(*, backend_dir: Path | None = None) -> None:
    """
    Load ~/.stripe-installer/app-secrets.env into os.environ.
    Local file wins over backend/.env for installer keys (never committed).
    """
    if backend_dir is None:
        backend_dir = Path(__file__).resolve().parents[2]

    migrate_app_secrets_from_backend_env(backend_dir / ".env")
    values = parse_env_file(app_secrets_path())
    for key, value in values.items():
        if key in APP_SECRET_KEYS:
            os.environ[key] = value
