"""Per-project vault backup under ~/.stripe-installer/projects/ (never in git)."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidTag

from apps.stripe_installer.portfolio_paths import portfolio_data_dir

from .crypto import EncryptedPayload, decrypt_secret

if TYPE_CHECKING:
    from apps.projects.models import Project

    from .models import VaultSecret

logger = logging.getLogger(__name__)

LOCAL_VAULT_VERSION = 1
PROJECTS_SUBDIR = "projects"


def local_vault_path(project_slug: str) -> Path:
    directory = portfolio_data_dir() / PROJECTS_SUBDIR / project_slug
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "vault.json"


def _read_document(project_slug: str) -> dict | None:
    path = local_vault_path(project_slug)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read local vault %s: %s", path, exc)
        return None


def _write_document(project_slug: str, document: dict) -> None:
    path = local_vault_path(project_slug)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def save_secret_to_local(project: Project, secret: VaultSecret, salt: bytes) -> None:
    document = _read_document(project.slug) or {
        "version": LOCAL_VAULT_VERSION,
        "salt": base64.b64encode(salt).decode("ascii"),
        "secrets": {},
    }
    document["version"] = LOCAL_VAULT_VERSION
    document["salt"] = base64.b64encode(salt).decode("ascii")
    document.setdefault("secrets", {})
    document["secrets"][secret.key_name] = {
        "encrypted_value": secret.encrypted_value,
        "iv": secret.iv,
        "auth_tag": secret.auth_tag,
        "display_mask": secret.display_mask,
        "key_mode": secret.key_mode,
        "verified": secret.verified,
        "verification_message": secret.verification_message,
    }
    _write_document(project.slug, document)


def delete_secret_from_local(project: Project, key_name: str) -> None:
    document = _read_document(project.slug)
    if not document:
        return
    secrets = document.get("secrets") or {}
    if key_name not in secrets:
        return
    del secrets[key_name]
    document["secrets"] = secrets
    if secrets:
        _write_document(project.slug, document)
    else:
        path = local_vault_path(project.slug)
        if path.is_file():
            path.unlink()


def load_secret_from_local(project: Project, key_name: str) -> str | None:
    document = _read_document(project.slug)
    if not document:
        return None
    entry = (document.get("secrets") or {}).get(key_name)
    salt_b64 = document.get("salt")
    if not entry or not salt_b64:
        return None
    payload = EncryptedPayload(
        encrypted_value=entry["encrypted_value"],
        iv=entry["iv"],
        auth_tag=entry["auth_tag"],
    )
    try:
        return decrypt_secret(payload, base64.b64decode(salt_b64))
    except InvalidTag:
        logger.warning("Local vault secret %s:%s cannot be decrypted", project.slug, key_name)
        return None


def list_local_secret_keys(project_slug: str) -> list[str]:
    document = _read_document(project_slug)
    if not document:
        return []
    return sorted((document.get("secrets") or {}).keys())


def sync_project_from_local_store(project: Project) -> list[str]:
    """Pull secrets from ~/.stripe-installer into the database vault."""
    from .models import _persist_secret, get_or_create_vault

    document = _read_document(project.slug)
    if not document:
        return []

    salt_b64 = document.get("salt")
    secrets_map = document.get("secrets") or {}
    if not salt_b64 or not secrets_map:
        return []

    salt = base64.b64decode(salt_b64)
    vault = get_or_create_vault(project)
    if bytes(vault.salt) != salt:
        vault.salt = salt
        vault.save(update_fields=["salt"])

    imported: list[str] = []
    for key_name, entry in secrets_map.items():
        payload = EncryptedPayload(
            encrypted_value=entry["encrypted_value"],
            iv=entry["iv"],
            auth_tag=entry["auth_tag"],
        )
        try:
            plaintext = decrypt_secret(payload, salt)
        except InvalidTag:
            continue
        _persist_secret(project, key_name, plaintext)
        imported.append(key_name)
    return imported
