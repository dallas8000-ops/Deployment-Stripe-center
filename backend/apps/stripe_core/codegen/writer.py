"""Write generated files to project root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.projects.models import Project


@dataclass
class WriteResult:
    path: str
    action: str  # created | updated | skipped


def write_codegen_files(
    project: "Project",
    repo_root: Path,
    files: dict[str, str],
    *,
    force: bool = False,
) -> list[WriteResult]:
    """Write codegen output, relocating app paths for Django/Flask monorepos."""
    from apps.stripe_core.codegen.paths import relocate_codegen_paths, codegen_backend_prefix

    prefix = codegen_backend_prefix(project, repo_root)
    relocated = relocate_codegen_paths(files, project.framework, prefix)
    return write_project_files(repo_root, relocated, force=force)


def write_project_files(
    project_root: Path,
    files: dict[str, str],
    *,
    force: bool = False,
) -> list[WriteResult]:
    results: list[WriteResult] = []
    for rel_path, content in sorted(files.items()):
        dest = project_root / rel_path
        existed = dest.is_file()
        if existed and not force:
            results.append(WriteResult(rel_path, "skipped"))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        results.append(WriteResult(rel_path, "updated" if existed else "created"))
    return results
