"""Connect GitHub to Railway services and trigger redeploys (hub automation)."""

from __future__ import annotations

from typing import Any

from apps.deploy.env_push import _railway_environment_id, _railway_gql
from apps.projects.models import Project


def github_repo_slug(project: Project) -> str | None:
    git_url = (project.git_url or "").strip().rstrip("/")
    if "github.com/" in git_url:
        return git_url.split("github.com/", 1)[-1].removesuffix(".git")
    return None


def railway_service_repo(token: str, service_id: str) -> dict[str, str | None]:
    data = _railway_gql(
        token,
        """
        query($id: String!) {
          service(id: $id) {
            id
            name
            repoTriggers { edges { node { branch repository } } }
          }
        }
        """,
        {"id": service_id},
    )
    service = data.get("service") or {}
    trigger = ((service.get("repoTriggers") or {}).get("edges") or [{}])[0].get("node", {})
    repo = str(trigger.get("repository") or "").strip() or None
    branch = str(trigger.get("branch") or "").strip() or None
    return {"name": service.get("name"), "repo": repo, "branch": branch}


def connect_railway_github(
    token: str,
    service_id: str,
    repo: str,
    *,
    branch: str = "main",
) -> None:
    _railway_gql(
        token,
        """
        mutation($id: String!, $input: ServiceConnectInput!) {
          serviceConnect(id: $id, input: $input) { id }
        }
        """,
        {"id": service_id, "input": {"repo": repo, "branch": branch}},
    )


def trigger_railway_deploy(token: str, project_id: str, service_id: str) -> str | None:
    env_id = _railway_environment_id(token, project_id)
    deploy_data = _railway_gql(
        token,
        """
        mutation($serviceId: String!, $environmentId: String!) {
          serviceInstanceDeployV2(serviceId: $serviceId, environmentId: $environmentId)
        }
        """,
        {"serviceId": service_id, "environmentId": env_id},
    )
    payload = deploy_data.get("serviceInstanceDeployV2") or {}
    if isinstance(payload, dict):
        return str(payload.get("id") or "") or None
    return str(payload) if payload else None


def ensure_railway_github_and_deploy(
    project: Project,
    token: str,
    project_id: str,
    service_id: str,
    *,
    branch: str = "main",
    trigger_deploy: bool = True,
) -> dict[str, Any]:
    """
    Ensure the Railway web service is linked to the project's GitHub repo, then redeploy.

    The hub's env push alone does not build new code — Railway needs either a connected repo
    (git push → deploy) or an explicit serviceInstanceDeployV2 after env changes.
    """
    result: dict[str, Any] = {"repoConnected": False, "deployTriggered": False}
    repo_slug = github_repo_slug(project)
    current = railway_service_repo(token, service_id)
    result["currentRepo"] = current.get("repo")
    result["currentBranch"] = current.get("branch")

    if not current.get("repo"):
        if not repo_slug:
            result["message"] = (
                "Railway service has no GitHub repo — set git_url on the hub project "
                "or connect the repo in Railway → Settings → Source."
            )
            return result
        connect_railway_github(token, service_id, repo_slug, branch=branch)
        result["repoConnected"] = True
        result["connectedRepo"] = repo_slug
        result["connectedBranch"] = branch

    if trigger_deploy:
        dep_id = trigger_railway_deploy(token, project_id, service_id)
        result["deployTriggered"] = bool(dep_id)
        result["deploymentId"] = dep_id
        result["message"] = (
            f"GitHub connected and deploy triggered ({dep_id})"
            if result.get("repoConnected") and dep_id
            else f"Redeploy triggered ({dep_id})"
            if dep_id
            else "Could not trigger Railway deploy"
        )
    elif result.get("repoConnected"):
        result["message"] = f"Connected GitHub repo {repo_slug} — push {branch} to deploy"
    else:
        result["message"] = "GitHub repo already connected — push to deploy"

    return result
