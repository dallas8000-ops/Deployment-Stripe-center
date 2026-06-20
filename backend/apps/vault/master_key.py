"""Resolve VAULT_MASTER_KEY from local-only storage (never committed to git)."""

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


def resolve_vault_master_key() -> str:
    """
    Master key resolution order:
    1. ~/.stripe-installer/vault-master-key (default — survives setup / .env resets)
    2. VAULT_MASTER_KEY env var (Railway / explicit override); persisted to file when file missing
    3. Generate a new key and write to ~/.stripe-installer/
    """
    path = master_key_path()
    file_key = ""
    if path.is_file():
        file_key = path.read_text(encoding="utf-8").strip()

    env_key = os.environ.get("VAULT_MASTER_KEY", "").strip()

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


def _write_master_key_file(path: Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
