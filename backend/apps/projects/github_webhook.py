"""GitHub App webhook — PR events trigger readiness checks."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from django.conf import settings

from apps.projects.audit import log_audit
from apps.projects.github_app import create_check_run, github_app_configured
from apps.projects.github_ci import run_readiness_gate
from apps.projects.models import Project


def verify_github_signature(payload: bytes, signature_header: str | None) -> bool:
    secret = getattr(settings, "GITHUB_WEBHOOK_SECRET", "")
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def _normalize_repo_url(owner: str, repo: str) -> str:
    return f"github.com/{owner}/{repo}".lower()


def find_project_for_repo(owner: str, repo: str) -> Project | None:
    needle = _normalize_repo_url(owner, repo)
    for project in Project.objects.exclude(git_url="").select_related("organization"):
        url = (project.git_url or "").lower()
        if needle in url:
            return project
    return None


def handle_pull_request(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action")
    if action not in ("opened", "synchronize", "reopened"):
        return {"skipped": True, "reason": f"action={action}"}

    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}
    owner = (repo.get("owner") or {}).get("login") or ""
    repo_name = repo.get("name") or ""
    head_sha = (pr.get("head") or {}).get("sha") or ""

    if not owner or not repo_name or not head_sha:
        return {"skipped": True, "reason": "missing repo or head sha"}

    project = find_project_for_repo(owner, repo_name)
    if not project:
        return {"skipped": True, "reason": "no matching project git_url"}

    installation_id = (payload.get("installation") or {}).get("id")
    org = project.organization
    if org and org.github_installation_id:
        installation_id = org.github_installation_id

    try:
        result = run_readiness_gate(project)
    except (ValueError, FileNotFoundError) as exc:
        result = {"passed": False, "score": 0, "label": str(exc), "checks": [], "failingCount": 0}

    log_audit(
        project,
        "github.pr_readiness",
        detail={
            "action": action,
            "headSha": head_sha,
            "passed": result.get("passed"),
            "score": result.get("score"),
        },
    )

    check_result = None
    if github_app_configured() and installation_id:
        try:
            conclusion = "success" if result.get("passed") else "failure"
            summary = (
                f"Score: {result.get('score')} — {result.get('label')}\n"
                f"Failing checks: {result.get('failingCount', 0)}"
            )
            check_result = create_check_run(
                installation_id,
                owner,
                repo_name,
                head_sha=head_sha,
                conclusion=conclusion,
                summary=summary,
            )
        except RuntimeError as exc:
            check_result = {"error": str(exc)}

    return {
        "project": project.slug,
        "passed": result.get("passed"),
        "score": result.get("score"),
        "checkRun": check_result,
    }


def handle_installation(payload: dict[str, Any]) -> dict[str, Any]:
    from apps.organizations.models import Organization

    action = payload.get("action")
    installation = payload.get("installation") or {}
    installation_id = installation.get("id")
    account = installation.get("account") or {}
    account_login = account.get("login") or ""

    linked_org = None
    if installation_id:
        org = Organization.objects.filter(github_installation_id=installation_id).first()
        if org and account_login and org.github_account != account_login:
            org.github_account = account_login
            org.save(update_fields=["github_account", "updated_at"])
            linked_org = org.slug

    return {
        "installation": True,
        "action": action,
        "installationId": installation_id,
        "account": account_login,
        "linkedOrg": linked_org,
    }


def dispatch_github_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event_type == "pull_request":
        return handle_pull_request(payload)
    if event_type == "installation":
        return handle_installation(payload)
    return {"skipped": True, "reason": f"unhandled event {event_type}"}
