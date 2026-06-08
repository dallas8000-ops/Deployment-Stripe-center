"""GitHub pull request helper for generated Stripe setup files."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from apps.projects.git_clone import _authenticated_url, _git_subprocess_env, parse_github_repo, validate_git_url
from apps.projects.models import Project
from apps.vault.models import get_secret

BRANCH_PREFIX = "stripe-installer"


def _github_api(token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:400]
        raise RuntimeError(f"GitHub API {exc.code}: {detail}") from exc


def _default_branch(token: str, owner: str, repo: str) -> str:
    meta = _github_api(token, "GET", f"/repos/{owner}/{repo}")
    return meta.get("default_branch") or "main"


def create_setup_pull_request(
    project: Project,
    *,
    commit_message: str = "chore: Stripe Installer setup",
    pr_title: str | None = None,
    pr_body: str | None = None,
) -> dict:
    if not project.local_path:
        raise ValueError("Project local_path is required")
    root = Path(project.local_path).resolve()
    if not root.is_dir() or not (root / ".git").is_dir():
        raise ValueError("Project path is not a git repository")

    token = get_secret(project, "GITHUB_TOKEN") or get_secret(project, "GIT_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN or GIT_TOKEN required in vault for pull requests")

    git_url = validate_git_url(project.git_url)
    parsed = parse_github_repo(git_url)
    if not parsed:
        raise ValueError("Pull requests require a GitHub repository URL")
    owner, repo = parsed
    repo = re.sub(r"\.git$", "", repo)

    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    if not status.stdout.strip():
        raise ValueError("No changes to commit — run pipeline or deploy prep first")

    branch = f"{BRANCH_PREFIX}/setup"
    base = _default_branch(token, owner, repo)
    env = _git_subprocess_env(project)
    auth_url = _authenticated_url(git_url, project)

    subprocess.run(["git", "-C", str(root), "remote", "set-url", "origin", auth_url], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "checkout", "-B", branch], check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", commit_message],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    push = subprocess.run(
        ["git", "-C", str(root), "push", "-u", "origin", branch, "--force"],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    if push.returncode != 0:
        raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push failed")

    title = pr_title or f"Stripe Installer setup — {project.name}"
    body = pr_body or (
        "Automated Stripe setup from [Stripe Installer](https://github.com).\n\n"
        "Includes codegen, deploy config, and readiness artifacts."
    )

    existing = _github_api(
        token,
        "GET",
        f"/repos/{owner}/{repo}/pulls?head={owner}:{branch}&state=open",
    )
    if isinstance(existing, list) and existing:
        pr = existing[0]
        return {
            "action": "existing",
            "url": pr["html_url"],
            "number": pr["number"],
            "branch": branch,
        }

    pr = _github_api(
        token,
        "POST",
        f"/repos/{owner}/{repo}/pulls",
        {"title": title, "body": body, "head": branch, "base": base},
    )
    return {
        "action": "created",
        "url": pr["html_url"],
        "number": pr["number"],
        "branch": branch,
    }
