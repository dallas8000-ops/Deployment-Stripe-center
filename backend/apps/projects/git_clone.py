"""Git pull in the project's real folder — never clone into the Automation Center repo."""

from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
from pathlib import Path

from django.conf import settings

from apps.projects.models import Project
from apps.stripe_core.portfolio_workspace import require_project_folder, workspace_path_error
from apps.vault.models import get_secret

_GIT_URL = re.compile(r"^(https?://|git@|ssh://)", re.I)
_GITHUB_HTTPS = re.compile(r"^https://(?:[^@]+@)?github\.com/([^/]+)/([^/.]+)", re.I)


def validate_git_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("git_url is required")
    if not _GIT_URL.match(cleaned):
        raise ValueError("git_url must be https://, git@, or ssh://")
    return cleaned


def parse_github_repo(git_url: str) -> tuple[str, str] | None:
    if git_url.startswith("git@github.com:"):
        match = re.match(r"git@github\.com:([^/]+)/([^/.]+?)(?:\.git)?$", git_url)
        return (match.group(1), match.group(2)) if match else None
    match = _GITHUB_HTTPS.match(git_url)
    return (match.group(1), match.group(2)) if match else None


def _resolve_git_token(project: Project) -> str | None:
    return (
        get_secret(project, "GITHUB_TOKEN")
        or get_secret(project, "GIT_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GIT_TOKEN")
    )


def _authenticated_url(git_url: str, project: Project) -> str:
    token = _resolve_git_token(project)
    if not token or not git_url.startswith("https://"):
        return git_url
    parsed = urllib.parse.urlparse(git_url)
    host = parsed.hostname or ""
    if "github.com" in host or "gitlab.com" in host:
        netloc = f"x-access-token:{urllib.parse.quote(token, safe='')}@{host}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urllib.parse.urlunparse(parsed._replace(netloc=netloc))
    return git_url


def _git_subprocess_env(project: Project) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    ssh_key = os.environ.get("GIT_SSH_KEY_PATH") or getattr(settings, "GIT_SSH_KEY_PATH", "")
    if ssh_key and Path(ssh_key).is_file():
        env["GIT_SSH_COMMAND"] = (
            f'ssh -i "{ssh_key}" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
        )

    creds_path = os.environ.get("GIT_CREDENTIALS_PATH") or getattr(settings, "GIT_CREDENTIALS_PATH", "")
    if creds_path and Path(creds_path).is_file():
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "credential.helper"
        env["GIT_CONFIG_VALUE_0"] = f"store --file={creds_path}"

    return env


def pull_project_repo(project: Project) -> dict:
    """git pull --ff-only in the project's local_path. Does not clone new repos."""
    validate_git_url(project.git_url)
    err = workspace_path_error(project)
    if err:
        raise ValueError(err)
    dest = require_project_folder(project)
    if not (dest / ".git").is_dir():
        raise ValueError(
            f"{dest} is not a git repository. Clone your app there manually, then set local_path in Settings."
        )

    env = _git_subprocess_env(project)
    pull = subprocess.run(
        ["git", "-C", str(dest), "pull", "--ff-only"],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if pull.returncode != 0:
        hint = ""
        if "Authentication failed" in (pull.stderr or "") or "403" in (pull.stderr or ""):
            hint = " — store GITHUB_TOKEN or GIT_TOKEN in vault"
        raise RuntimeError((pull.stderr.strip() or pull.stdout.strip() or "git pull failed") + hint)

    project.local_path = str(dest)
    project.save(update_fields=["local_path", "updated_at"])
    return {
        "action": "updated",
        "local_path": project.local_path,
        "git_url": project.git_url,
        "authenticated": bool(env.get("GIT_SSH_COMMAND")),
    }
