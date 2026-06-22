"""TOTP MFA — enroll, verify, recovery codes, login challenge tokens."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass

import pyotp
from django.core import signing
from django.utils import timezone

from apps.vault.crypto import EncryptedPayload, decrypt_secret, encrypt_secret

CHALLENGE_SALT = "accounts.mfa.challenge"
CHALLENGE_MAX_AGE_SECONDS = 300
RECOVERY_CODE_COUNT = 10


@dataclass
class MfaEnrollStart:
    secret: str
    provisioning_uri: str
    issuer: str


def _user_salt(user_id: int) -> bytes:
    return hashlib.sha256(f"accounts-mfa:{user_id}".encode()).digest()


def encrypt_mfa_secret(user_id: int, secret: str) -> str:
    payload = encrypt_secret(secret, _user_salt(user_id))
    return json.dumps(
        {
            "encrypted_value": payload.encrypted_value,
            "iv": payload.iv,
            "auth_tag": payload.auth_tag,
        }
    )


def decrypt_mfa_secret(user_id: int, stored: str) -> str:
    raw = json.loads(stored)
    payload = EncryptedPayload(
        encrypted_value=raw["encrypted_value"],
        iv=raw["iv"],
        auth_tag=raw["auth_tag"],
    )
    return decrypt_secret(payload, _user_salt(user_id))


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, *, email: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    normalized = (code or "").strip().replace(" ", "")
    if not normalized.isdigit() or len(normalized) != 6:
        return False
    return bool(pyotp.TOTP(secret).verify(normalized, valid_window=valid_window))


def generate_recovery_codes() -> tuple[list[str], list[str]]:
    """Return (plaintext codes for one-time display, sha256 hashes for storage)."""
    plain: list[str] = []
    hashed: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        code = f"{secrets.token_hex(4)}-{secrets.token_hex(4)}".upper()
        plain.append(code)
        hashed.append(_hash_recovery_code(code))
    return plain, hashed


def _hash_recovery_code(code: str) -> str:
    normalized = code.strip().upper().replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def consume_recovery_code(user, code: str) -> bool:
    normalized_hash = _hash_recovery_code(code)
    stored: list[str] = list(user.mfa_recovery_codes_hash or [])
    if normalized_hash not in stored:
        return False
    stored.remove(normalized_hash)
    user.mfa_recovery_codes_hash = stored
    user.save(update_fields=["mfa_recovery_codes_hash"])
    return True


def issue_mfa_challenge(user_id: int) -> str:
    return signing.TimestampSigner(salt=CHALLENGE_SALT).sign(str(user_id))


def resolve_mfa_challenge(token: str) -> int:
    user_id = signing.TimestampSigner(salt=CHALLENGE_SALT).unsign(
        token, max_age=CHALLENGE_MAX_AGE_SECONDS
    )
    return int(user_id)


def mfa_issuer_name() -> str:
    from django.conf import settings

    return getattr(settings, "MFA_ISSUER_NAME", "Automation Center")
