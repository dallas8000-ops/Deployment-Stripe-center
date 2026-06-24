"""GitHub CI status and readiness gate helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps.deploy.postgres import get_production_url
from apps.projects.github_pr import _default_branch, _github_api
from apps.projects.git_clone import parse_github_repo
from apps.projects.models import Project
from apps.stripe_core.readiness import readiness_label, run_readiness_checks, score_readiness
from apps.vault.models import get_secret

GITHUB_CI_WORKFLOW = """name: Stripe Installer readiness

on:
  pull_request:
  push:
    branches: [main, master]

jobs:
  stripe-readiness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Stripe Installer readiness gate
        env:
          STRIPE_INSTALLER_URL: ${{ secrets.STRIPE_INSTALLER_URL }}
          STRIPE_INSTALLER_PROJECT: ${{ secrets.STRIPE_INSTALLER_PROJECT }}
          STRIPE_INSTALLER_API_KEY: ${{ secrets.STRIPE_INSTALLER_API_KEY }}
        run: |
          set -euo pipefail
          if [ -z "${STRIPE_INSTALLER_URL:-}" ] || [ -z "${STRIPE_INSTALLER_API_KEY:-}" ]; then
            echo "Configure STRIPE_INSTALLER_URL and STRIPE_INSTALLER_API_KEY repository secrets"
            exit 1
          fi
          PROJECT="${STRIPE_INSTALLER_PROJECT:-}"
          if [ -z "$PROJECT" ]; then
            echo "Set STRIPE_INSTALLER_PROJECT to your project slug"
            exit 1
          fi
          RESP=$(curl -sf -X POST \\
            "${STRIPE_INSTALLER_URL%/}/api/v1/ci/readiness/" \\
            -H "Authorization: Bearer ${STRIPE_INSTALLER_API_KEY}" \\
            -H "Content-Type: application/json" \\
            -d "{\\"project\\":\\"${PROJECT}\\"}")
          echo "$RESP"
          echo "$RESP" | grep -q '"passed": true' || exit 1
"""


def _github_token(project: Project) -> str:
    token = get_secret(project, "GITHUB_TOKEN") or get_secret(project, "GIT_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN or GIT_TOKEN required in vault")
    return token


def _repo_parts(project: Project) -> tuple[str, str]:
    parsed = parse_github_repo(project.git_url or "")
    if not parsed:
        raise ValueError("Project git_url must be a GitHub repository")
    owner, repo = parsed
    return owner, repo.replace(".git", "")


def get_github_ci_status(project: Project, ref: str | None = None) -> dict[str, Any]:
    token = _github_token(project)
    owner, repo = _repo_parts(project)
    ref = ref or _default_branch(token, owner, repo)

    combined = _github_api(token, "GET", f"/repos/{owner}/{repo}/commits/{ref}/status")
    check_runs = _github_api(token, "GET", f"/repos/{owner}/{repo}/commits/{ref}/check-runs")

    runs = []
    if isinstance(check_runs, dict):
        for row in check_runs.get("check_runs") or []:
            runs.append(
                {
                    "name": row.get("name"),
                    "status": row.get("status"),
                    "conclusion": row.get("conclusion"),
                    "htmlUrl": row.get("html_url"),
                }
            )

    state = combined.get("state") or "unknown"
    return {
        "ref": ref,
        "state": state,
        "success": state == "success",
        "statusesUrl": combined.get("statuses_url"),
        "checkRuns": runs,
        "repository": f"{owner}/{repo}",
    }


def run_readiness_gate(project: Project, *, app_url: str = "") -> dict[str, Any]:
    if not project.local_path:
        raise ValueError("Project local_path is required for readiness gate")

    root = Path(project.local_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project path not found: {root}")

    prod = get_production_url(project, app_url)
    checks = run_readiness_checks(project, root, production_url=prod)
    score = score_readiness(checks)
    failing = [c for c in checks if c.status == "fail"]
    passed = score >= 70 and len(failing) == 0

    return {
        "passed": passed,
        "score": score,
        "label": readiness_label(score),
        "checks": [c.to_dict() for c in checks],
        "failingCount": len(failing),
    }
