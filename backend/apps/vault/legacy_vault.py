"""Decrypt secrets from the legacy Node CLI vault (.stripe-installer/vault.enc.json)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

LEGACY_VAULT_REL = Path(".stripe-installer") / "vault.enc.json"
LEGACY_SALT_REL = Path(".stripe-installer") / "vault.salt"


def legacy_vault_paths(project_root: Path) -> tuple[Path, Path]:
    return project_root / LEGACY_VAULT_REL, project_root / LEGACY_SALT_REL


def legacy_vault_exists(project_root: Path) -> bool:
    vault_path, salt_path = legacy_vault_paths(project_root)
    return vault_path.is_file() and salt_path.is_file()


def list_legacy_vault_keys(project_root: Path) -> list[str]:
    vault_path, _ = legacy_vault_paths(project_root)
    if not vault_path.is_file():
        return []
    try:
        data = json.loads(vault_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    return sorted(data.keys())


def decrypt_legacy_vault(
    project_root: Path,
    passphrase: str,
) -> dict[str, str]:
    """Return plaintext key/value pairs from the legacy Node SecretVault."""
    vault_path, salt_path = legacy_vault_paths(project_root)
    if not vault_path.is_file() or not salt_path.is_file():
        raise FileNotFoundError(f"Legacy vault not found under {project_root / '.stripe-installer'}")

    salt = salt_path.read_bytes()
    entries = json.loads(vault_path.read_text(encoding="utf-8"))
    if not isinstance(entries, dict):
        raise ValueError("Invalid legacy vault.enc.json format")

    key = hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )

    plaintexts: dict[str, str] = {}
    for key_name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        try:
            iv = base64.b64decode(entry["iv"])
            ciphertext = base64.b64decode(entry["encryptedValue"])
            auth_tag = base64.b64decode(entry["authTag"])
            aesgcm = AESGCM(key)
            value = aesgcm.decrypt(iv, ciphertext + auth_tag, None).decode("utf-8")
            plaintexts[key_name] = value
        except (KeyError, InvalidTag, ValueError):
            continue

    if not plaintexts:
        raise ValueError("Legacy vault found but passphrase did not decrypt any keys")
    return plaintexts
