"""Map generated file paths for Django/Flask monorepos (manage.py under backend/)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.projects.models import Project

FRAMEWORKS_WITH_BACKEND_PREFIX = frozenset({"django", "flask"})

_BACKEND_RELATIVE_PREFIXES: dict[str, tuple[str, ...]] = {
    "django": ("stripe_billing/",),
    "flask": ("stripe_routes.py", "templates/stripe/"),
}


def codegen_backend_prefix(project: "Project", repo_root: Path) -> str:
    """Relative path from repo root to the API package (e.g. backend)."""
    from apps.stripe_core.portfolio_workspace import relative_scan_root, resolve_scan_root

    scan_data = project.scan_data or {}
    cached = str(scan_data.get("scanBackendPath") or "").strip().strip("/")
    if cached:
        return cached
    if project.framework not in FRAMEWORKS_WITH_BACKEND_PREFIX:
        return ""
    return relative_scan_root(repo_root, resolve_scan_root(repo_root)).strip("/")


def relocate_codegen_paths(
    files: dict[str, str],
    framework: str,
    backend_prefix: str,
) -> dict[str, str]:
    """Prefix app code paths when Django/Flask lives under backend/ (not repo root)."""
    if not backend_prefix or framework not in FRAMEWORKS_WITH_BACKEND_PREFIX:
        return files
    prefixes = _BACKEND_RELATIVE_PREFIXES.get(framework, ())
    out: dict[str, str] = {}
    for rel_path, content in files.items():
        if any(rel_path.startswith(p) for p in prefixes):
            out[f"{backend_prefix}/{rel_path}"] = content
        else:
            out[rel_path] = content
    return out


def resolve_stripe_module_path(project: "Project", repo_root: Path) -> Path:
    """stripe/views.py location — repo root or backend/stripe_billing/ for monorepos."""
    prefix = codegen_backend_prefix(project, repo_root)
    if prefix:
        return repo_root / prefix / "stripe_billing" / "views.py"
    return repo_root / "stripe_billing" / "views.py"


def existing_backend_dockerfile(repo_root: Path, backend_prefix: str) -> bool:
    if not backend_prefix:
        return False
    return (repo_root / backend_prefix / "Dockerfile").is_file()


def filter_infra_paths(
    files: dict[str, str],
    project: "Project",
    repo_root: Path,
) -> dict[str, str]:
    """Relocate monorepo paths and skip root Dockerfile when backend/Dockerfile exists."""
    prefix = codegen_backend_prefix(project, repo_root)
    out = relocate_codegen_paths(files, project.framework, prefix)
    if prefix and existing_backend_dockerfile(repo_root, prefix):
        out.pop("Dockerfile", None)
    return out
