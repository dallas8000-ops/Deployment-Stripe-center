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
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
        "RAILWAY_ENVIRONMENT_ID",
        "GITHUB_TOKEN",
        "GIT_TOKEN",
    }
)

ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

ENV_FILE_CANDIDATES = (
    ".env.local",
    ".env",
    ".env.production",
    "backend/.env",
    "api/.env",
)

STRIPE_VAULT_KEYS = (
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
)


def is_importable_key(key: str) -> bool:
    if key in IMPORT_KEYS:
        return True
    upper = key.upper()
    if upper.endswith("_SECRET_KEY") or upper.endswith("_WEBHOOK_SECRET"):
        return True
    if upper.endswith("_PUBLISHABLE_KEY") or upper.startswith("NEXT_PUBLIC_STRIPE"):
        return True
    if key in ("DATABASE_URL", "REDIS_URL"):
        return True
    if upper.endswith("_API_TOKEN") or upper.endswith("_ACCESS_TOKEN"):
        return True
    return False


def find_env_file(project_root: Path, env_file: str | None = None) -> Path | None:
    if env_file and env_file != "auto":
        path = project_root / env_file
        return path if path.is_file() else None
    for name in ENV_FILE_CANDIDATES:
        path = project_root / name
        if path.is_file():
            return path
    return None


def import_env_to_vault(project: Project, project_root: Path, env_file: str = "auto") -> list[str]:
    if env_file == "auto":
        path = find_env_file(project_root)
        if not path:
            raise FileNotFoundError(
                f"No env file found in {project_root} (tried {', '.join(ENV_FILE_CANDIDATES)})"
            )
    else:
        path = project_root / env_file
        if not path.is_file():
            raise FileNotFoundError(f"Env file not found: {env_file}")

    env_label = path.relative_to(project_root).as_posix()

    imported: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE.match(stripped)
        if not match:
            continue
        key, raw = match.group(1), match.group(2).strip()
        if key not in IMPORT_KEYS and not is_importable_key(key):
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
        raise ValueError(f"No importable keys found in {env_label}")
    return imported


def auto_import_env_to_vault(project: Project, project_root: Path) -> list[str]:
    """Import from the first existing env file under the project root."""
    return import_env_to_vault(project, project_root, env_file="auto")


def hydrate_vault_from_env(project: Project, project_root: Path) -> list[str]:
    """
    Re-import Stripe keys from disk when vault entries are missing or unreadable.
    Safe to call before pipeline verify — only writes keys found in env files.
    """
    from apps.vault.models import get_secret, is_secret_readable, VaultSecret

    needs_import = False
    for key in STRIPE_VAULT_KEYS:
        if not get_secret(project, key):
            needs_import = True
            break
    if not needs_import:
        unreadable = any(
            not is_secret_readable(project, s)
            for s in VaultSecret.objects.filter(project=project)
        )
        needs_import = unreadable
    if not needs_import:
        return []
    return auto_import_env_to_vault(project, project_root)
