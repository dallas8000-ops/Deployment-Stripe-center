"""Re-encrypt all vault secrets when rotating VAULT_MASTER_KEY."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.vault.crypto import EncryptedPayload, VaultConfigurationError, decrypt_secret, encrypt_secret
from apps.vault.models import ProjectVault, VaultSecret


@dataclass
class RotationResult:
    projects: int
    secrets: int
    dry_run: bool


def _key_bytes_from_raw(raw: str) -> bytes:
    import base64
    import binascii

    raw = raw.strip()
    if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return bytes.fromhex(raw)
    try:
        key = base64.b64decode(raw)
    except binascii.Error as exc:
        raise VaultConfigurationError("Key must be 64-char hex or base64 of 32 bytes") from exc
    if len(key) != 32:
        raise VaultConfigurationError("Key must decode to exactly 32 bytes")
    return key


def rotate_vault_master_key(new_master_key_raw: str, *, dry_run: bool = False) -> RotationResult:
    old_raw = settings.VAULT_MASTER_KEY
    if not old_raw:
        raise VaultConfigurationError("VAULT_MASTER_KEY is not set")
    old_key = _key_bytes_from_raw(old_raw)
    new_key = _key_bytes_from_raw(new_master_key_raw)
    if old_key == new_key:
        raise VaultConfigurationError("New key is identical to current key")

    project_count = 0
    secret_count = 0

    for vault in ProjectVault.objects.select_related("project").all():
        project_count += 1
        salt = bytes(vault.salt)
        for secret in VaultSecret.objects.filter(project=vault.project):
            payload = EncryptedPayload(
                encrypted_value=secret.encrypted_value,
                iv=secret.iv,
                auth_tag=secret.auth_tag,
            )
            plaintext = decrypt_secret(payload, salt, master_key=old_key)
            secret_count += 1
            if dry_run:
                continue
            new_payload = encrypt_secret(plaintext, salt, master_key=new_key)
            secret.encrypted_value = new_payload.encrypted_value
            secret.iv = new_payload.iv
            secret.auth_tag = new_payload.auth_tag
            secret.save(update_fields=["encrypted_value", "iv", "auth_tag", "updated_at"])

    return RotationResult(projects=project_count, secrets=secret_count, dry_run=dry_run)
