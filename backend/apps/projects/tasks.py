from __future__ import annotations

from celery import shared_task

from apps.projects.models import Project


@shared_task(bind=True, name="projects.clone_repo")
def clone_repo_task(self, project_id: str, branch: str | None = None, force: bool = False) -> dict:
    from apps.projects.git_clone import clone_project_repo

    project = Project.objects.get(id=project_id)
    return clone_project_repo(project, branch=branch, force=force)
