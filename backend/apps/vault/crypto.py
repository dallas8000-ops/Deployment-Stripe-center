"""AES-256-GCM encryption — compatible layout with Node SecretVault (iv + authTag + ciphertext)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


class VaultConfigurationError(Exception):
    pass


@dataclass
class EncryptedPayload:
    encrypted_value: str
    iv: str
    auth_tag: str


def _master_key_bytes() -> bytes:
    raw = settings.VAULT_MASTER_KEY.strip()
    if not raw:
        raise VaultConfigurationError(
            "VAULT_MASTER_KEY is not set. Generate: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return bytes.fromhex(raw)
    try:
        key = base64.b64decode(raw)
    except binascii.Error as exc:
        raise VaultConfigurationError("VAULT_MASTER_KEY must be 64-char hex or base64 of 32 bytes") from exc
    if len(key) != 32:
        raise VaultConfigurationError("VAULT_MASTER_KEY must decode to exactly 32 bytes")
    return key


def derive_project_key(salt: bytes, master_key: bytes | None = None) -> bytes:
    """scrypt(master, salt, 32) — matches Node SecretVault key derivation intent."""
    key_material = master_key if master_key is not None else _master_key_bytes()
    return hashlib.scrypt(
        key_material,
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )


def generate_salt() -> bytes:
    return os.urandom(32)


def encrypt_secret(plaintext: str, project_salt: bytes, master_key: bytes | None = None) -> EncryptedPayload:
    key = derive_project_key(project_salt, master_key)
    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    auth_tag = ciphertext_with_tag[-16:]
    ciphertext = ciphertext_with_tag[:-16]
    return EncryptedPayload(
        encrypted_value=base64.b64encode(ciphertext).decode("ascii"),
        iv=base64.b64encode(iv).decode("ascii"),
        auth_tag=base64.b64encode(auth_tag).decode("ascii"),
    )


def decrypt_secret(payload: EncryptedPayload, project_salt: bytes, master_key: bytes | None = None) -> str:
    key = derive_project_key(project_salt, master_key)
    iv = base64.b64decode(payload.iv)
    ciphertext = base64.b64decode(payload.encrypted_value)
    auth_tag = base64.b64decode(payload.auth_tag)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext + auth_tag, None)
    return plaintext.decode("utf-8")
