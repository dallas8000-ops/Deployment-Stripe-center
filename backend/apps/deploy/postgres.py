"""PostgreSQL schema and status — ported from legacy Node deploy/postgres.ts."""

from __future__ import annotations

import re
from pathlib import Path

from apps.projects.models import Project
from apps.vault.models import get_secret

DATABASE_URL_PATTERN = re.compile(r"^postgres(ql)?://", re.I)


def get_database_url(project: Project) -> str | None:
    return get_secret(project, "DATABASE_URL")


def postgres_status(project: Project) -> dict:
    url = get_database_url(project)
    valid = bool(url and DATABASE_URL_PATTERN.match(url))
    return {
        "configured": valid,
        "message": "DATABASE_URL set in vault" if valid else "Store DATABASE_URL in vault (postgresql://…)",
    }


def schema_sql() -> str:
    template = (
        Path(__file__).resolve().parents[1]
        / "stripe_engine"
        / "codegen"
        / "templates"
        / "shared"
        / "schema.sql.j2"
    )
    return template.read_text(encoding="utf-8")
