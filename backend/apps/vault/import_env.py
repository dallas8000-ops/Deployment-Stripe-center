"""Import secrets from .env files into the vault (write-only)."""

from __future__ import annotations

import re
from pathlib import Path

from apps.projects.models import Project
from apps.vault.models import get_secret, set_secret

IMPORT_KEYS = frozenset(
    {
        "STRIPE_SECRET_KEY",
        "STRIPE_PUBLISHABLE_KEY",
        "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DATABASE_URL",
        "NEON_API_KEY",
        "SUPABASE_ACCESS_TOKEN",
        "SUPABASE_ORG_ID",
        "RAILWAY_API_TOKEN",
        "GITHUB_TOKEN",
        "GIT_TOKEN",
    }
)

ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def import_env_to_vault(project: Project, project_root: Path, env_file: str = ".env.local") -> list[str]:
    path = project_root / env_file
    if not path.is_file():
        raise FileNotFoundError(f"Env file not found: {env_file}")

    imported: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE.match(stripped)
        if not match:
            continue
        key, raw = match.group(1), match.group(2).strip()
        if key not in IMPORT_KEYS:
            continue
        value = raw.strip().strip('"').strip("'")
        if not value:
            continue
        set_secret(project, key, value)
        imported.append(key)

    if "STRIPE_PUBLISHABLE_KEY" in imported and "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY" not in imported:
        pk = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
        if pk:
            set_secret(project, "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", pk)
            imported.append("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY")

    if not imported:
        raise ValueError(f"No importable keys found in {env_file}")
    return imported
