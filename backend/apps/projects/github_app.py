"""GitHub App authentication — JWT and installation tokens."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings


def github_app_configured() -> bool:
    return bool(
        getattr(settings, "GITHUB_APP_ID", "")
        and getattr(settings, "GITHUB_APP_PRIVATE_KEY", "")
    )


def _private_key_pem() -> str:
    raw = getattr(settings, "GITHUB_APP_PRIVATE_KEY", "")
    if not raw:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY not configured")
    return raw.replace("\\n", "\n")


def create_app_jwt() -> str:
    import jwt

    app_id = getattr(settings, "GITHUB_APP_ID", "")
    if not app_id:
        raise RuntimeError("GITHUB_APP_ID not configured")

    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
    return jwt.encode(payload, _private_key_pem(), algorithm="RS256")


def _github_app_api(method: str, path: str, body: dict | None = None, token: str | None = None) -> Any:
    auth = token or create_app_jwt()
    prefix = "Bearer" if token else "Bearer"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"{prefix} {auth}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:400]
        raise RuntimeError(f"GitHub App API {exc.code}: {detail}") from exc


def get_installation_token(installation_id: int | str) -> str:
    result = _github_app_api(
        "POST",
        f"/app/installations/{installation_id}/access_tokens",
    )
    token = result.get("token")
    if not token:
        raise RuntimeError("Installation token missing from GitHub response")
    return token


def create_check_run(
    installation_id: int | str,
    owner: str,
    repo: str,
    *,
    head_sha: str,
    name: str = "Stripe Installer readiness",
    status: str = "completed",
    conclusion: str = "success",
    title: str = "Stripe readiness",
    summary: str = "",
) -> dict:
    token = get_installation_token(installation_id)
    return _github_app_api(
        "POST",
        f"/repos/{owner}/{repo}/check-runs",
        {
            "name": name,
            "head_sha": head_sha,
            "status": status,
            "conclusion": conclusion,
            "output": {"title": title, "summary": summary or title},
        },
        token=token,
    )
