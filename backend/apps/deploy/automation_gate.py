"""Shared automation steps before pipeline/deploy runs."""

from __future__ import annotations

from typing import Any

from apps.projects.models import Project
from apps.stripe_installer.hub_keys import HUB_SLUG


def run_automation_before_pipeline(
    project: Project,
    *,
    user,
    hub_bootstrap: bool = True,
) -> dict[str, Any]:
    """
    Run built-in automation before queuing a pipeline.

    Hub: full platform bootstrap (pin master key, sync all projects, push Railway env).
    Other projects: prepare vault/platform and optional deploy automation.
    """
    from apps.deploy.platform_bootstrap import (
        automate_project_deploy,
        bootstrap_platform_automation,
        prepare_project_automation,
    )

    result: dict[str, Any] = {"hub": project.slug == HUB_SLUG, "steps": []}

    prep = prepare_project_automation(project, user=user)
    result["prep"] = prep

    if project.slug == HUB_SLUG and hub_bootstrap:
        bootstrap = bootstrap_platform_automation(project, user=user)
        result["bootstrap"] = bootstrap
        result["ok"] = bootstrap.get("ok", False)
        result["message"] = bootstrap.get("message", "")
        return result

    if project.slug != HUB_SLUG:
        deploy_auto = automate_project_deploy(project, user=user)
        result["deployAutomation"] = deploy_auto
        result["ok"] = deploy_auto.get("ok", False)
        result["message"] = (
            "Deploy automation complete"
            if deploy_auto.get("ok")
            else "Deploy automation finished with issues — see steps"
        )
        return result

    result["ok"] = True
    result["message"] = "Automation prep complete"
    return result
