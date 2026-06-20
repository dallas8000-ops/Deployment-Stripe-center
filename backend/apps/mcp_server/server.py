"""MCP server for Stripe Installer — stdio tools over Django ORM."""

from __future__ import annotations

import json
import os
import sys


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _user_from_env():
    from django.contrib.auth import get_user_model

    email = os.environ.get("STRIPE_INSTALLER_USER", "").strip()
    if not email:
        raise RuntimeError("Set STRIPE_INSTALLER_USER to your account email")
    User = get_user_model()
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        raise RuntimeError(f"No user found for {email}")
    return user


def _tool_list_projects(_args: dict) -> dict:
    from apps.core.access import projects_for_user

    user = _user_from_env()
    rows = []
    for project in projects_for_user(user).distinct()[:50]:
        rows.append(
            {
                "slug": project.slug,
                "name": project.name,
                "framework": project.framework,
                "organization": project.organization.slug if project.organization_id else None,
            }
        )
    return {"projects": rows}


def _tool_readiness(args: dict) -> dict:
    from apps.core.access import get_project_for_user
    from apps.projects.github_ci import run_readiness_gate

    slug = args.get("project_slug") or args.get("slug")
    if not slug:
        raise ValueError("project_slug is required")
    user = _user_from_env()
    project = get_project_for_user(user, slug, min_role="viewer")
    return run_readiness_gate(project)


def _tool_drift(args: dict) -> dict:
    from apps.core.access import get_project_for_user
    from apps.diagnostics.drift import detect_drift

    slug = args.get("project_slug") or args.get("slug")
    if not slug:
        raise ValueError("project_slug is required")
    user = _user_from_env()
    project = get_project_for_user(user, slug, min_role="viewer")
    return detect_drift(project)


def _tool_vault_status(args: dict) -> dict:
    from apps.core.access import get_project_for_user
    from apps.vault.models import ProjectVault, list_vault_entries

    slug = args.get("project_slug") or args.get("slug")
    if not slug:
        raise ValueError("project_slug is required")
    user = _user_from_env()
    project = get_project_for_user(user, slug, min_role="viewer")
    return {
        "project": project.slug,
        "initialized": ProjectVault.objects.filter(project=project).exists(),
        "entries": list_vault_entries(project),
    }


def _tool_start_pipeline(args: dict) -> dict:
    from apps.core.access import get_project_for_user
    from apps.runs.models import PipelineRun
    from apps.runs.tasks import execute_pipeline

    slug = args.get("project_slug") or args.get("slug")
    if not slug:
        raise ValueError("project_slug is required")
    user = _user_from_env()
    project = get_project_for_user(user, slug, min_role="member")
    if not project.local_path:
        raise ValueError("Set project local_path before running the pipeline")

    options = {k: v for k, v in args.items() if k not in ("project_slug", "slug")}
    run = PipelineRun.objects.create(project=project, started_by=user, options=options)
    execute_pipeline.delay(str(run.id))
    return {"runId": str(run.id), "status": run.status, "project": project.slug}


def _tool_open_pr_prep(args: dict) -> dict:
    import subprocess
    from pathlib import Path

    from apps.core.access import get_project_for_user
    from apps.projects.github_ci import run_readiness_gate
    from apps.vault.models import get_secret, list_secret_keys

    slug = args.get("project_slug") or args.get("slug")
    if not slug:
        raise ValueError("project_slug is required")
    user = _user_from_env()
    project = get_project_for_user(user, slug, min_role="member")

    readiness = run_readiness_gate(project)
    has_git_token = bool(get_secret(project, "GITHUB_TOKEN") or get_secret(project, "GIT_TOKEN"))
    dirty_files: list[str] = []
    if project.local_path:
        root = Path(project.local_path).resolve()
        if (root / ".git").is_dir():
            status = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=False,
            )
            dirty_files = [line[3:] for line in status.stdout.splitlines() if line.strip()]

    body_lines = [
        "## Stripe Installer setup",
        "",
        f"Readiness score: **{readiness.get('score')}** — {readiness.get('label')}",
        "",
        "### Checks",
    ]
    for check in readiness.get("checks") or []:
        body_lines.append(f"- [{check.get('status')}] {check.get('id')}: {check.get('message')}")

    return {
        "project": project.slug,
        "readiness": readiness,
        "hasGitToken": has_git_token,
        "vaultKeys": list_secret_keys(project),
        "dirtyFiles": dirty_files,
        "canOpenPr": has_git_token and bool(dirty_files),
        "suggestedTitle": "chore: Stripe Installer setup",
        "suggestedBody": "\n".join(body_lines),
    }


def _tool_diagnose(args: dict) -> dict:
    from pathlib import Path

    from apps.core.access import get_project_for_user
    from apps.diagnostics.diagnostics import run_diagnostics

    slug = args.get("project_slug") or args.get("slug")
    if not slug:
        raise ValueError("project_slug is required")
    user = _user_from_env()
    project = get_project_for_user(user, slug, min_role="viewer")
    if not project.local_path:
        raise ValueError("Project local_path not set")
    report = run_diagnostics(project, Path(project.local_path).resolve())
    return report.to_dict()


TOOLS = {
    "list_projects": {
        "description": "List Stripe Installer projects accessible to STRIPE_INSTALLER_USER",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": _tool_list_projects,
    },
    "project_readiness": {
        "description": "Run readiness gate for a project slug",
        "inputSchema": {
            "type": "object",
            "properties": {"project_slug": {"type": "string"}},
            "required": ["project_slug"],
        },
        "handler": _tool_readiness,
    },
    "project_drift": {
        "description": "Check Stripe catalog drift for a project",
        "inputSchema": {
            "type": "object",
            "properties": {"project_slug": {"type": "string"}},
            "required": ["project_slug"],
        },
        "handler": _tool_drift,
    },
    "project_diagnose": {
        "description": "Run Stripe health diagnose for a project",
        "inputSchema": {
            "type": "object",
            "properties": {"project_slug": {"type": "string"}},
            "required": ["project_slug"],
        },
        "handler": _tool_diagnose,
    },
    "project_vault_status": {
        "description": "Masked vault entries for a project (no plaintext secrets)",
        "inputSchema": {
            "type": "object",
            "properties": {"project_slug": {"type": "string"}},
            "required": ["project_slug"],
        },
        "handler": _tool_vault_status,
    },
    "start_pipeline": {
        "description": "Queue a Stripe Installer pipeline run for a project",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string"},
                "skip_deploy": {"type": "boolean"},
            },
            "required": ["project_slug"],
        },
        "handler": _tool_start_pipeline,
    },
    "project_open_pr_prep": {
        "description": "Readiness + suggested PR title/body before opening a setup PR",
        "inputSchema": {
            "type": "object",
            "properties": {"project_slug": {"type": "string"}},
            "required": ["project_slug"],
        },
        "handler": _tool_open_pr_prep,
    },
}


def _handle_request(msg: dict) -> dict | None:
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "stripe-installer", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        tools = []
        for name, spec in TOOLS.items():
            tools.append(
                {
                    "name": name,
                    "description": spec["description"],
                    "inputSchema": spec["inputSchema"],
                }
            )
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}

    if method == "tools/call":
        params = msg.get("params") or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        spec = TOOLS.get(tool_name)
        if not spec:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        try:
            result = spec["handler"](arguments)
            text = json.dumps(result, indent=2)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": text}]},
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True},
            }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_stdio_server() -> None:
    _setup_django()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle_request(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
