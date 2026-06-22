"""Redis distributed locks for singleton work across replicas."""

from __future__ import annotations

import secrets
import time
from contextlib import contextmanager
from typing import Iterator

from django.conf import settings


def _redis_client():
    import redis

    return redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)


def _lock_key(name: str) -> str:
    return f"stripe-installer:lock:{name}"


@contextmanager
def distributed_lock(
    name: str,
    *,
    ttl_seconds: int = 300,
    blocking: bool = False,
    blocking_timeout_seconds: float = 5.0,
) -> Iterator[bool]:
    """
    Yield True when the lock was acquired, False when another holder exists.
    Skips locking when Redis infra is disabled (local dev shortcuts).
    """
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False) or settings.CHANNEL_LAYERS["default"][
        "BACKEND"
    ].endswith("InMemoryChannelLayer"):
        yield True
        return

    client = _redis_client()
    key = _lock_key(name)
    token = secrets.token_hex(16)
    deadline = time.monotonic() + max(0.0, blocking_timeout_seconds)

    acquired = False
    try:
        while True:
            acquired = bool(client.set(key, token, nx=True, ex=max(1, ttl_seconds)))
            if acquired or not blocking:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        yield acquired
    finally:
        if acquired:
            # Release only if we still own the lock (compare token).
            pipe = client.pipeline(True)
            while True:
                try:
                    pipe.watch(key)
                    if client.get(key) == token.encode():
                        pipe.multi()
                        pipe.delete(key)
                        pipe.execute()
                    else:
                        pipe.reset()
                    break
                except Exception:
                    pipe.reset()
                    break


def beat_singleton(lock_name: str, *, ttl_seconds: int = 3600):
    """Decorator: only one replica runs a scheduled all-projects Celery task."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            with distributed_lock(f"beat:{lock_name}", ttl_seconds=ttl_seconds, blocking=False) as acquired:
                if not acquired:
                    return {"skipped": True, "reason": "lock held by another replica"}
                return func(*args, **kwargs)

        wrapper.__name__ = getattr(func, "__name__", "wrapped")
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
