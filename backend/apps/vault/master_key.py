"""Resolve VAULT_MASTER_KEY from env (production) or local-only file (dev)."""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from apps.stripe_installer.portfolio_paths import portfolio_data_dir

logger = logging.getLogger(__name__)

MASTER_KEY_FILENAME = "vault-master-key"


def master_key_path() -> Path:
    return portfolio_data_dir() / MASTER_KEY_FILENAME


def _on_railway() -> bool:
    return bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PUBLIC_DOMAIN"))


def resolve_vault_master_key() -> str:
    """
    Master key resolution:

    **Railway / ephemeral containers** (``RAILWAY_*`` set):
      1. ``VAULT_MASTER_KEY`` env var — required for durable secrets; never shadowed by disk
      2. Key file under ``STRIPE_INSTALLER_DATA_DIR`` / ``~/.stripe-installer/`` (same container only)
      3. Generate ephemeral key (existing vault secrets become unreadable after next deploy)

    **Local dev** (durable home directory):
      1. ``~/.stripe-installer/vault-master-key`` — survives ``.env`` resets
      2. ``VAULT_MASTER_KEY`` env — persisted to file when file missing
      3. Generate and write to ``~/.stripe-installer/``
    """
    path = master_key_path()
    file_key = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    env_key = os.environ.get("VAULT_MASTER_KEY", "").strip()

    if _on_railway():
        return _resolve_for_railway(path, env_key, file_key)

    if file_key:
        if env_key and env_key != file_key:
            logger.info(
                "Using vault master key from %s (VAULT_MASTER_KEY in environment differs)",
                path,
            )
        return file_key

    if env_key:
        _write_master_key_file(path, env_key)
        logger.info("Persisted VAULT_MASTER_KEY to %s", path)
        return env_key

    key = secrets.token_hex(32)
    _write_master_key_file(path, key)
    logger.info("Generated new vault master key at %s", path)
    return key


def _resolve_for_railway(path: Path, env_key: str, file_key: str) -> str:
    if env_key:
        if file_key and file_key != env_key:
            logger.warning(
                "Railway: using VAULT_MASTER_KEY from environment (ignoring key file at %s)",
                path,
            )
        return env_key

    if file_key:
        logger.warning(
            "Railway: VAULT_MASTER_KEY env not set; using key file at %s "
            "(ephemeral — secrets may not survive redeploy)",
            path,
        )
        return file_key

    key = secrets.token_hex(32)
    logger.error(
        "Railway: VAULT_MASTER_KEY not set; generated ephemeral key. "
        "Set a permanent 64-char hex VAULT_MASTER_KEY in Railway Variables "
        "or previously encrypted secrets will be unreadable after redeploy."
    )
    return key


def _write_master_key_file(path: Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
