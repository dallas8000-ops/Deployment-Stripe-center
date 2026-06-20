"""Resolve organization context for API Transfer operations."""

from __future__ import annotations

from apps.organizations.models import Membership, Organization
from apps.projects.models import Project


def organization_for_user(user, project: Project | None = None) -> Organization | None:
    if project and project.organization_id:
        return project.organization
    membership = Membership.objects.filter(user=user).select_related("organization").first()
    return membership.organization if membership else None
