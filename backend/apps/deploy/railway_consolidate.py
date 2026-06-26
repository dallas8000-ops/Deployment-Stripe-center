"""Move a portfolio app from a standalone Railway project into a shared monorepo project."""

from __future__ import annotations

import subprocess
import time
from typing import Any

from apps.deploy.env_push import (
    _railway_environment_id,
    _railway_gql,
    get_railway_env_vars,
    push_to_railway,
)
from apps.deploy.railway_deploy import (
    connect_railway_github,
    railway_service_repo,
    trigger_railway_deploy,
)
from apps.deploy.railway_resolve import (
    _list_railway_projects_with_domains,
    remember_railway_targets,
)
from apps.projects.models import Project


def _find_project(projects: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    target = name.strip().lower()
    for proj in projects:
        if (proj.get("name") or "").strip().lower() == target:
            return proj
    return None


def _find_service(project: dict[str, Any], *names: str) -> dict[str, Any] | None:
    targets = {n.strip().lower() for n in names if n}
    for svc in project.get("services") or []:
        if (svc.get("name") or "").strip().lower() in targets:
            return svc
    return None


def _service_delete(token: str, service_id: str) -> None:
    _railway_gql(
        token,
        "mutation($id: String!) { serviceDelete(id: $id) }",
        {"id": service_id},
    )


def _project_delete(token: str, project_id: str) -> None:
    _railway_gql(
        token,
        "mutation($id: String!) { projectDelete(id: $id) }",
        {"id": project_id},
    )


def _create_postgres(token: str, project_id: str, name: str) -> str:
    data = _railway_gql(
        token,
        """
        mutation($input: ServiceCreateInput!) {
          serviceCreate(input: $input) { id }
        }
        """,
        {
            "input": {
                "projectId": project_id,
                "name": name,
                "source": {"image": "postgres:16-alpine"},
            }
        },
    )
    service_id = str((data.get("serviceCreate") or {}).get("id") or "").strip()
    if not service_id:
        raise RuntimeError(f"Failed to create Postgres service '{name}'")
    return service_id


def _create_empty_service(token: str, project_id: str, name: str) -> str:
    data = _railway_gql(
        token,
        """
        mutation($input: ServiceCreateInput!) {
          serviceCreate(input: $input) { id }
        }
        """,
        {"input": {"projectId": project_id, "name": name}},
    )
    service_id = str((data.get("serviceCreate") or {}).get("id") or "").strip()
    if not service_id:
        raise RuntimeError(f"Failed to create service '{name}'")
    return service_id


def _wait_postgres_url(
    token: str,
    project_id: str,
    service_id: str,
    *,
    timeout_sec: int = 180,
) -> str:
    env_id = _railway_environment_id(token, project_id)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        vars_map = get_railway_env_vars(token, project_id, service_id, env_id)
        for key in ("DATABASE_URL", "DATABASE_PRIVATE_URL", "DATABASE_PUBLIC_URL"):
            url = (vars_map.get(key) or "").strip()
            if url.startswith(("postgres://", "postgresql://")):
                return url
        time.sleep(4)
    raise RuntimeError("Postgres DATABASE_URL not available after provisioning")


def _postgres_public_url(token: str, project_id: str, service_id: str) -> str:
    env_id = _railway_environment_id(token, project_id)
    vars_map = get_railway_env_vars(token, project_id, service_id, env_id)
    for key in ("DATABASE_PUBLIC_URL", "DATABASE_URL"):
        url = (vars_map.get(key) or "").strip()
        if url.startswith(("postgres://", "postgresql://")):
            return url
    raise RuntimeError("Could not resolve source Postgres connection URL")


def _copy_database(source_url: str, dest_url: str) -> None:
    """pg_dump | psql via local binaries or Docker postgres image."""
    dump_cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "postgres:16-alpine",
        "pg_dump",
        "--no-owner",
        "--no-acl",
        source_url,
    ]
    dump = subprocess.run(dump_cmd, capture_output=True, check=False)
    if dump.returncode != 0:
        dump = subprocess.run(
            ["pg_dump", "--no-owner", "--no-acl", source_url],
            capture_output=True,
            check=False,
        )
    if dump.returncode != 0:
        raise RuntimeError(
            "pg_dump failed — ensure Docker is running or install PostgreSQL client tools. "
            f"stderr: {dump.stderr.decode()[:300]}"
        )

    restore_cmd = ["docker", "run", "--rm", "-i", "postgres:16-alpine", "psql", dest_url]
    restore = subprocess.run(restore_cmd, input=dump.stdout, capture_output=True, check=False)
    if restore.returncode != 0:
        restore = subprocess.run(
            ["psql", dest_url],
            input=dump.stdout,
            capture_output=True,
            check=False,
        )
    if restore.returncode != 0:
        raise RuntimeError(
            "psql restore failed — migrate manually in Railway if needed. "
            f"stderr: {restore.stderr.decode()[:300]}"
        )


def consolidate_agripay_to_monorepo(
    project: Project,
    token: str,
    *,
    home_project_name: str = "hearty-enjoyment",
    source_project_name: str = "agripay-logistics-ai",
    duplicate_names: tuple[str, ...] = ("AgriPay-Logistics-AI",),
    source_web_name: str = "agripay-api",
    new_web_name: str = "agripay-api",
    new_postgres_name: str = "Postgres-AgriPay",
    production_domain: str = "agripay-api-production.up.railway.app",
    repo: str = "",
    branch: str = "main",
    dry_run: bool = False,
    skip_db_copy: bool = False,
    delete_source_project: bool = True,
) -> dict[str, Any]:
    """
    1. Delete stale AgriPay copy in the shared project.
    2. Recreate working web + Postgres in the shared project.
    3. Copy env + database, redeploy, repoint hub vault.
    4. Remove the standalone Railway project.
    """
    projects = _list_railway_projects_with_domains(token)
    home = _find_project(projects, home_project_name)
    source = _find_project(projects, source_project_name)
    if not home:
        raise RuntimeError(f"Home project '{home_project_name}' not found")
    if not source:
        raise RuntimeError(f"Source project '{source_project_name}' not found")

    home_id = home["id"]
    source_id = source["id"]
    source_web = _find_service(source, source_web_name)
    source_pg = _find_service(source, "Postgres", "PostgreSQL")
    if not source_web:
        raise RuntimeError(f"Source web service '{source_web_name}' not found")
    if not source_pg:
        raise RuntimeError("Source Postgres service not found")

    duplicate = None
    for name in duplicate_names:
        duplicate = _find_service(home, name)
        if duplicate:
            break

    repo_info = railway_service_repo(token, source_web["id"])
    repo_slug = (repo or repo_info.get("repo") or "").strip()
    branch = (branch or repo_info.get("branch") or "main").strip() or "main"
    if not repo_slug:
        raise RuntimeError("Could not resolve GitHub repo — pass --repo owner/name")

    plan = {
        "homeProject": home_project_name,
        "homeProjectId": home_id,
        "sourceProject": source_project_name,
        "sourceProjectId": source_id,
        "deleteDuplicate": duplicate,
        "sourceWeb": source_web,
        "sourcePostgres": source_pg,
        "newWebName": new_web_name,
        "newPostgresName": new_postgres_name,
        "repo": repo_slug,
        "branch": branch,
        "productionDomain": production_domain,
    }
    if dry_run:
        return {"dryRun": True, "plan": plan}

    if duplicate:
        _service_delete(token, duplicate["id"])

    new_pg_id = _create_postgres(token, home_id, new_postgres_name)
    dest_db_url = _wait_postgres_url(token, home_id, new_pg_id)

    if not skip_db_copy:
        source_db_url = _postgres_public_url(token, source_id, source_pg["id"])
        _copy_database(source_db_url, dest_db_url)

    new_web_id = _create_empty_service(token, home_id, new_web_name)
    env_id = _railway_environment_id(token, home_id)
    source_env = get_railway_env_vars(token, source_id, source_web["id"], env_id)
    copied = dict(source_env)
    copied["DATABASE_URL"] = "${{" + new_postgres_name + ".DATABASE_URL}}"
    push_to_railway(token, home_id, new_web_id, copied, env_id, preserve_existing=False)

    connect_railway_github(token, new_web_id, repo_slug, branch=branch)
    deploy_id = trigger_railway_deploy(token, home_id, new_web_id)

    remember_railway_targets(project, home_id, new_web_id, overwrite=True)

    if delete_source_project:
        _service_delete(token, source_web["id"])
        _service_delete(token, source_pg["id"])
        _project_delete(token, source_id)

    return {
        "homeProjectId": home_id,
        "webServiceId": new_web_id,
        "postgresServiceId": new_pg_id,
        "deploymentId": deploy_id,
        "dashboardUrl": f"https://railway.app/project/{home_id}/service/{new_web_id}",
        "deletedDuplicate": duplicate.get("name") if duplicate else None,
        "deletedSourceProject": source_project_name if delete_source_project else None,
        "message": (
            f"AgriPay consolidated into {home_project_name}. "
            f"Open {home_project_name} in Railway — service '{new_web_name}' should get "
            f"{production_domain} after the old standalone project is removed."
        ),
    }
