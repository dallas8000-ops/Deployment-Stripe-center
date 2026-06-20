"""Merge project vault secrets into deploy pipeline requests."""

from __future__ import annotations

from apps.projects.models import Project
from apps.vault.services import get_project_secret, list_project_secret_keys


def hydrate_deploy_request(project: Project, request_data: dict) -> dict:
    """Add non-sensitive env keys from vault; secrets stay in secrets list for pipeline."""
    data = dict(request_data)
    env = dict(data.get("environment", {}))
    secrets = list(data.get("secrets", []))
    existing_secret_keys = {s.get("key") for s in secrets if s.get("key")}

    for key in list_project_secret_keys(project):
        if key in env or key in existing_secret_keys:
            continue
        value = get_project_secret(project, key)
        if not value:
            continue
        secrets.append({"key": key, "value": value})
        existing_secret_keys.add(key)

    data["environment"] = env
    data["secrets"] = secrets
    if not data.get("repoUrl") and project.git_url:
        data["repoUrl"] = project.git_url
    return data
