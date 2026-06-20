"""Discover and import secrets from every known installer storage location."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from apps.stripe_installer.portfolio_paths import portfolio_data_dir
from apps.vault.import_env import ENV_FILE_CANDIDATES, ENV_LINE, IMPORT_KEYS, is_importable_key
from apps.vault.legacy_vault import decrypt_legacy_vault, legacy_vault_exists, list_legacy_vault_keys
from apps.vault.local_store import list_local_secret_keys, local_vault_path

if TYPE_CHECKING:
    from apps.projects.models import Project

SourceStatus = Literal["ready", "missing", "needs_passphrase", "empty"]
SourceKind = Literal["local_store", "legacy_vault", "env_file", "portfolio_path"]

ENV_RELATIVE_PATHS = ENV_FILE_CANDIDATES


@dataclass
class SecretSource:
    kind: SourceKind
    label: str
    path: str
    status: SourceStatus
    key_count: int
    keys: list[str]
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "path": self.path,
            "status": self.status,
            "keyCount": self.key_count,
            "keys": self.keys,
            "note": self.note,
        }


def _count_importable_keys_in_env(path: Path) -> list[str]:
    if not path.is_file():
        return []
    found: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE.match(stripped)
        if not match:
            continue
        key = match.group(1)
        value = match.group(2).strip().strip('"').strip("'")
        if value and is_importable_key(key):
            found.append(key)
    return sorted(set(found))


def resolve_project_root(project: Project) -> Path | None:
    """Project DB path, then portfolio-registry localPath."""
    if project.local_path:
        root = Path(project.local_path).expanduser().resolve()
        if root.is_dir():
            return root

    try:
        from apps.stripe_installer.portfolio_registry import load_registry

        for app in load_registry():
            if app.project_slug == project.slug and app.local_path:
                root = Path(app.local_path).expanduser().resolve()
                if root.is_dir():
                    return root
    except (OSError, ValueError, ImportError):
        pass
    return None


def discover_secret_sources(project: Project) -> dict:
    """List every place this project may have stored secrets (no values returned)."""
    root = resolve_project_root(project)
    sources: list[SecretSource] = []

    local_keys = list_local_secret_keys(project.slug)
    local_path = local_vault_path(project.slug)
    sources.append(
        SecretSource(
            kind="local_store",
            label="Stripe Installer local vault",
            path=str(local_path),
            status="ready" if local_keys else ("missing" if not local_path.is_file() else "empty"),
            key_count=len(local_keys),
            keys=local_keys,
            note="Never synced to git — ~/.stripe-installer/projects/",
        )
    )

    if root:
        legacy_keys = list_legacy_vault_keys(root)
        legacy_path = root / ".stripe-installer" / "vault.enc.json"
        sources.append(
            SecretSource(
                kind="legacy_vault",
                label="Legacy Node CLI vault",
                path=str(legacy_path),
                status="needs_passphrase" if legacy_keys else "missing",
                key_count=len(legacy_keys),
                keys=legacy_keys,
                note="From stripe-installer vault unlock passphrase",
            )
        )

        for rel in ENV_RELATIVE_PATHS:
            env_path = root / rel
            keys = _count_importable_keys_in_env(env_path)
            if not keys and not env_path.is_file():
                continue
            sources.append(
                SecretSource(
                    kind="env_file",
                    label=rel,
                    path=str(env_path),
                    status="ready" if keys else "empty",
                    key_count=len(keys),
                    keys=keys,
                )
            )
    else:
        sources.append(
            SecretSource(
                kind="portfolio_path",
                label="Project folder",
                path=project.local_path or "",
                status="missing",
                key_count=0,
                keys=[],
                note="Set local_path on the project or add localPath in ~/.stripe-installer/portfolio-registry.json",
            )
        )

    return {
        "projectSlug": project.slug,
        "projectRoot": str(root) if root else None,
        "dataDir": str(portfolio_data_dir()),
        "localVaultPath": str(local_vault_path(project.slug)),
        "sources": [s.to_dict() for s in sources],
    }


def import_from_env_path(project: Project, env_path: Path) -> list[str]:
    if not env_path.is_file():
        return []
    from apps.vault.models import get_secret, set_secret

    imported: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE.match(stripped)
        if not match:
            continue
        key, raw = match.group(1), match.group(2).strip()
        if not is_importable_key(key):
            continue
        value = raw.strip().strip('"').strip("'")
        if not value:
            continue
        set_secret(project, key, value)
        imported.append(key)

    if "STRIPE_PUBLISHABLE_KEY" in imported:
        pk = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
        if pk and "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY" not in imported:
            set_secret(project, "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", pk)
            imported.append("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY")

    return sorted(set(imported))


def import_all_discovered_secrets(
    project: Project,
    *,
    legacy_passphrase: str | None = None,
    include_legacy: bool = True,
    include_env: bool = True,
    only_if_needed: bool = False,
) -> dict:
    """
    Import from legacy CLI vault, env files, then sync into ~/.stripe-installer/projects/{slug}/.
    """
    from apps.vault.import_env import STRIPE_VAULT_KEYS
    from apps.vault.models import get_or_create_vault, get_secret, set_secret, vault_health
    from apps.vault.local_store import sync_project_from_local_store

    get_or_create_vault(project)

    if only_if_needed:
        sync_project_from_local_store(project)
        health = vault_health(project)
        missing = any(not get_secret(project, k) for k in STRIPE_VAULT_KEYS)
        if health["masterKeyValid"] and health["totalCount"] and not missing:
            return {
                "imported": [],
                "importedBySource": {},
                "localVaultPath": str(local_vault_path(project.slug)),
                "projectRoot": str(resolve_project_root(project) or ""),
                "errors": [],
            }
    root = resolve_project_root(project)
    imported_by_source: dict[str, list[str]] = {}
    errors: list[str] = []

    if include_legacy and root and legacy_vault_exists(root):
        if not legacy_passphrase:
            errors.append(
                "Legacy vault at .stripe-installer/vault.enc.json requires your vault passphrase to import"
            )
        else:
            try:
                secrets = decrypt_legacy_vault(root, legacy_passphrase)
                keys: list[str] = []
                for key_name, value in secrets.items():
                    if is_importable_key(key_name) and value:
                        set_secret(project, key_name, value)
                        keys.append(key_name)
                imported_by_source["legacy_vault"] = sorted(set(keys))
            except (FileNotFoundError, ValueError) as exc:
                errors.append(str(exc))

    if include_env and root:
        for rel in ENV_RELATIVE_PATHS:
            env_path = root / rel
            if not env_path.is_file():
                continue
            try:
                keys = import_from_env_path(project, env_path)
                if keys:
                    imported_by_source[rel] = keys
            except OSError as exc:
                errors.append(f"{rel}: {exc}")

    # Ensure local store mirror is up to date
    sync_project_from_local_store(project)

    all_keys: list[str] = []
    seen: set[str] = set()
    for keys in imported_by_source.values():
        for key in keys:
            if key not in seen:
                seen.add(key)
                all_keys.append(key)

    return {
        "imported": all_keys,
        "importedBySource": imported_by_source,
        "localVaultPath": str(local_vault_path(project.slug)),
        "projectRoot": str(root) if root else None,
        "errors": errors,
    }
