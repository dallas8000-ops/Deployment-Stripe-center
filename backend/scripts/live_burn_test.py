#!/usr/bin/env python
"""Live burn test against running Django app (in-process, no HTTP server required)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, ok, detail))
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {label}"
    if detail:
        line += f" — {detail[:200]}"
    print(line)


def auth_client(email: str = "dallas8000@gmail.com") -> tuple[Client | None, str]:
    user = User.objects.filter(email=email).first()
    if not user:
        return None, f"user not found: {email}"
    token = str(RefreshToken.for_user(user).access_token)
    client = Client(HTTP_HOST="127.0.0.1")
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return client, ""


def get_json(client: Client, path: str, method: str = "GET", body: dict | None = None):
    if method == "GET":
        return client.get(path)
    return client.post(path, data=json.dumps(body or {}), content_type="application/json")


def main() -> int:
    print("\n=== Deployment-Stripe-center live burn test ===\n")

    # Health (no auth)
    anon = Client(HTTP_HOST="127.0.0.1")
    r = anon.get("/health/")
    record("GET /health/", r.status_code == 200, f"status={r.status_code}")

    client, err = auth_client()
    if not client:
        record("auth", False, err)
        return 1
    record("auth", True, "JWT for dallas8000@gmail.com")

    r = get_json(client, "/api/v1/auth/me/")
    record("GET /api/v1/auth/me/", r.status_code == 200, f"status={r.status_code}")

    r = get_json(client, "/api/v1/projects/")
    ok = r.status_code == 200
    detail = f"status={r.status_code}"
    slugs: list[str] = []
    if ok:
        data = r.json()
        items = data if isinstance(data, list) else data.get("results", data)
        slugs = [p.get("slug", "") for p in items if isinstance(p, dict)]
        detail += f", count={len(slugs)}"
        hidden = {"api-transfer", "kistie-store", "blog-2", "react-store-catalog"}
        leaked = [s for s in slugs if s in hidden]
        if leaked:
            ok = False
            detail += f", hidden leaked: {leaked}"
        elif len(slugs) != 7:
            detail += f" (expected 7 billing projects)"
    record("GET /api/v1/projects/", ok, detail)

    r = get_json(client, "/api/v1/transfer/status/")
    record("GET /api/v1/transfer/status/", r.status_code == 200, f"status={r.status_code}")

    r = get_json(client, "/api/v1/transfer/providers/status/")
    record("GET /api/v1/transfer/providers/status/", r.status_code == 200, f"status={r.status_code}")

    r = get_json(client, "/api/v1/transfer/audit/")
    record("GET /api/v1/transfer/audit/", r.status_code == 200, f"status={r.status_code}")

    hub_slug = "stripe-installer"
    for slug in [hub_slug, "elite-fintech-systems", "righand"]:
        if slug not in slugs and slugs:
            record(f"skip {slug}", True, "not in project list")
            continue

        r = get_json(client, f"/api/v1/projects/{slug}/setup-hub/")
        record(f"GET setup-hub [{slug}]", r.status_code == 200, f"status={r.status_code}")

        r = get_json(client, f"/api/v1/projects/{slug}/vault/keys/")
        ok = r.status_code == 200
        detail = f"status={r.status_code}"
        if ok:
            keys = r.json()
            key_names = list(keys.keys()) if isinstance(keys, dict) else []
            detail += f", keys={len(key_names)}"
        record(f"GET vault/keys [{slug}]", ok, detail)

        r = get_json(client, f"/api/v1/projects/{slug}/verify/", "POST")
        record(f"POST verify [{slug}]", r.status_code == 200, f"status={r.status_code}")

        r = get_json(client, f"/api/v1/projects/{slug}/stripe/config/")
        record(f"GET stripe/config [{slug}]", r.status_code == 200, f"status={r.status_code}")

    # Read-only setup-hub audit (no destructive actions)
    if hub_slug in slugs or not slugs:
        r = get_json(
            client,
            f"/api/v1/projects/{hub_slug}/setup-hub/actions/",
            "POST",
            {"action": "audit"},
        )
        ok = r.status_code == 200
        detail = f"status={r.status_code}"
        if ok:
            body = r.json()
            detail += f", keys={list(body.keys())[:6]}"
        record("POST setup-hub audit [hub]", ok, detail)

    failed = [x for x in RESULTS if not x[1]]
    passed = len(RESULTS) - len(failed)
    print(f"\n{'=' * 44}")
    print(f"Passed: {passed}/{len(RESULTS)}")
    if failed:
        print("\nFailures:")
        for label, _, detail in failed:
            print(f"  • {label}: {detail}")
        return 1
    print("\nAll live burn checks passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
