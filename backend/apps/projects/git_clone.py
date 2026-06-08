"""Clone or update a project git repository with private-repo credential support."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from django.conf import settings

from apps.projects.models import Project
from apps.vault.models import get_secret

_GIT_URL = re.compile(r"^(https?://|git@|ssh://)", re.I)
_GITHUB_HTTPS = re.compile(r"^https://(?:[^@]+@)?github\.com/([^/]+)/([^/.]+)", re.I)


def _clone_root() -> Path:
    root = Path(getattr(settings, "PROJECT_CLONE_ROOT", settings.BASE_DIR / "clones"))
    root.mkdir(parents=True, exist_ok=True)
    return root


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


def _set_clone_status(project: Project, status: str, *, error: str = "", extra: dict | None = None) -> None:
    scan = dict(project.scan_data or {})
    scan["cloneStatus"] = status
    scan["cloneError"] = error
    if extra:
        scan.update(extra)
    project.scan_data = scan
    project.save(update_fields=["scan_data", "updated_at"])


def clone_project_repo(
    project: Project,
    *,
    branch: str | None = None,
    force: bool = False,
) -> dict:
    git_url = validate_git_url(project.git_url)
    auth_url = _authenticated_url(git_url, project)
    dest = _clone_root() / project.slug
    env = _git_subprocess_env(project)

    _set_clone_status(project, "running")

    if dest.exists() and force:
        shutil.rmtree(dest)

    try:
        if dest.exists() and (dest / ".git").is_dir():
            pull = subprocess.run(
                ["git", "-C", str(dest), "pull", "--ff-only"],
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            if pull.returncode != 0:
                raise RuntimeError(pull.stderr.strip() or pull.stdout.strip() or "git pull failed")
            action = "updated"
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["git", "clone", "--depth", "1", auth_url, str(dest)]
            if branch:
                cmd = ["git", "clone", "--depth", "1", "-b", branch, auth_url, str(dest)]
            clone = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
            if clone.returncode != 0:
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                hint = ""
                if "Authentication failed" in (clone.stderr or "") or "403" in (clone.stderr or ""):
                    hint = " — store GITHUB_TOKEN or GIT_TOKEN in vault, or mount GIT_SSH_KEY_PATH / GIT_CREDENTIALS_PATH"
                raise RuntimeError(
                    (clone.stderr.strip() or clone.stdout.strip() or "git clone failed") + hint
                )
            action = "cloned"

        project.local_path = str(dest.resolve())
        project.save(update_fields=["local_path", "updated_at"])
        _set_clone_status(project, "completed", extra={"cloneAction": action})
        return {
            "action": action,
            "local_path": project.local_path,
            "git_url": git_url,
            "branch": branch,
            "authenticated": auth_url != git_url or bool(env.get("GIT_SSH_COMMAND")),
        }
    except Exception as exc:
        _set_clone_status(project, "failed", error=str(exc))
        raise
