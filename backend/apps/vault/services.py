"""
Shared vault access for all feature modules.

Stripe Installer, API Transfer, and deploy pipelines call these helpers —
never pass secrets through the frontend or between modules via HTTP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.projects.models import Project


def get_project_secret(project: Project, key_name: str) -> str | None:
    """Read a decrypted secret for a project (backend only)."""
    from apps.vault.models import get_secret

    return get_secret(project, key_name)


def set_project_secret(project: Project, key_name: str, value: str) -> None:
    """Store a secret for a project (encrypts + mirrors to ~/.stripe-installer)."""
    from apps.vault.models import set_secret

    set_secret(project, key_name, value)


def list_project_secret_keys(project: Project) -> list[str]:
    from apps.vault.models import list_secret_keys

    return list_secret_keys(project)
