"""Write-only display masks for vault secrets — never expose plaintext."""

from __future__ import annotations

import re

MASK_CHAR = "\u2022"  # •
MASK_TAIL_LEN = 12

_STRIPE_PREFIXES = (
    "sk_test_",
    "sk_live_",
    "pk_test_",
    "pk_live_",
    "rk_test_",
    "rk_live_",
    "whsec_",
)


def mask_secret_value(plaintext: str) -> str:
    """Return a 1Password-style masked display string."""
    if not plaintext:
        return MASK_CHAR * MASK_TAIL_LEN

    for prefix in _STRIPE_PREFIXES:
        if plaintext.startswith(prefix):
            return prefix + (MASK_CHAR * MASK_TAIL_LEN)

    if plaintext.startswith("postgresql://") or plaintext.startswith("postgres://"):
        return "postgresql://" + (MASK_CHAR * MASK_TAIL_LEN)

    # Generic: short visible prefix + bullets (never show meaningful secret body)
    if len(plaintext) <= 4:
        return MASK_CHAR * MASK_TAIL_LEN
    return plaintext[:4] + (MASK_CHAR * MASK_TAIL_LEN)


def detect_key_mode(plaintext: str) -> str:
    if "_live_" in plaintext or plaintext.startswith("whsec_"):
        # whsec doesn't have live/test in name — infer from paired keys later
        if "_live_" in plaintext:
            return "live"
    if "_test_" in plaintext:
        return "test"
    if re.match(r"^sk_live_", plaintext) or re.match(r"^pk_live_", plaintext):
        return "live"
    if re.match(r"^sk_test_", plaintext) or re.match(r"^pk_test_", plaintext):
        return "test"
    return "unknown"
