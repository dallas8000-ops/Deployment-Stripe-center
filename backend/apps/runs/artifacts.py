"""Resolve generated file contents for pipeline run downloads."""

from __future__ import annotations

from pathlib import Path

from apps.projects.models import Project
from apps.runs.models import PipelineRun
from apps.stripe_engine.codegen import generate_all
from apps.stripe_engine.provision import load_manifest


def resolve_run_files(run: PipelineRun) -> dict[str, str]:
    result = run.result or {}
    stored: dict[str, str] = result.get("generatedFiles") or {}
    if stored and any(content for content in stored.values()):
        return {path: content for path, content in stored.items() if content}

    project: Project = run.project
    if not project.local_path:
        return _regenerate(project, run)

    root = Path(project.local_path).resolve()
    files: dict[str, str] = {}
    for rel_path in result.get("filesWritten") or []:
        file_path = root / rel_path
        if file_path.is_file():
            files[rel_path] = file_path.read_text(encoding="utf-8")

    if files:
        return files

    return _regenerate(project, run)


def _regenerate(project: Project, run: PipelineRun) -> dict[str, str]:
    if not project.local_path:
        return {}
    root = Path(project.local_path).resolve()
    manifest = load_manifest(root)
    opts = run.options or {}
    return generate_all(
        project.framework,
        manifest,
        app_url=opts.get("app_url", "http://localhost:8000"),
        next_router=(project.scan_data or {}).get("nextRouter"),
    )
