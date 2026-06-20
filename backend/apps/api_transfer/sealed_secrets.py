"""Seal pipeline-stage secrets with the platform master key (not per-project vault salt)."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.vault.crypto import _master_key_bytes

_NONCE_BYTES = 12


@dataclass(frozen=True)
class SealedSecret:
    ciphertext: str
    nonce: str
    auth_tag: str

    def to_dict(self) -> dict[str, str]:
        return {"ciphertext": self.ciphertext, "nonce": self.nonce, "authTag": self.auth_tag}

    @classmethod
    def from_dict(cls, payload: dict[str, str]) -> "SealedSecret":
        return cls(
            ciphertext=payload["ciphertext"],
            nonce=payload["nonce"],
            auth_tag=payload["authTag"],
        )


def encrypt_secret(plaintext: str) -> SealedSecret:
    aesgcm = AESGCM(_master_key_bytes())
    nonce = AESGCM.generate_key(bit_length=128)[:_NONCE_BYTES]
    sealed = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    ciphertext, tag = sealed[:-16], sealed[-16:]
    return SealedSecret(
        ciphertext=base64.b64encode(ciphertext).decode("ascii"),
        nonce=base64.b64encode(nonce).decode("ascii"),
        auth_tag=base64.b64encode(tag).decode("ascii"),
    )


def decrypt_secret(sealed: SealedSecret) -> str:
    aesgcm = AESGCM(_master_key_bytes())
    nonce = base64.b64decode(sealed.nonce)
    ciphertext = base64.b64decode(sealed.ciphertext)
    tag = base64.b64decode(sealed.auth_tag)
    plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
    return plaintext.decode("utf-8")
