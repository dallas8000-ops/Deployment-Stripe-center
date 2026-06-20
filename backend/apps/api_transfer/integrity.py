"""Deterministic hashing for pipeline integrity and audit chains."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_stringify(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def integrity_hash(value: Any) -> str:
    return hashlib.sha256(stable_stringify(value).encode("utf-8")).hexdigest()
