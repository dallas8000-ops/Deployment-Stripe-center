"""Automated backup and recovery system for project configurations and manifests."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from apps.projects.models import Project


@dataclass
class BackupResult:
    """Result of a backup operation."""
    success: bool
    backup_id: str
    files_backed_up: list[str]
    size_bytes: int
    timestamp: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "backupId": self.backup_id,
            "filesBackedUp": self.files_backed_up,
            "sizeBytes": self.size_bytes,
            "timestamp": self.timestamp,
            "message": self.message,
        }


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""
    success: bool
    files_restored: list[str]
    timestamp: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "filesRestored": self.files_restored,
            "timestamp": self.timestamp,
            "message": self.message,
        }


def _get_backup_root() -> Path:
    """Get the root directory for backups."""
    from django.conf import settings

    backup_root = Path(settings.BASE_DIR) / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    return backup_root


def _get_project_backup_dir(project: Project) -> Path:
    """Get the backup directory for a specific project."""
    backup_root = _get_backup_root()
    project_dir = backup_root / str(project.id)
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def _generate_backup_id() -> str:
    """Generate a unique backup ID."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"backup_{timestamp}"


def create_project_backup(project: Project) -> BackupResult:
    """Create a backup of critical project files."""
    backup_id = _generate_backup_id()
    backup_dir = _get_project_backup_dir(project) / backup_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    root = Path(project.local_path).resolve() if project.local_path else None
    if not root or not root.is_dir():
        return BackupResult(
            success=False,
            backup_id=backup_id,
            files_backed_up=[],
            size_bytes=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            message="Project path not set or invalid",
        )

    files_to_backup = [
        ".stripe-installer/stripe-manifest.json",
        ".stripe-installer/deploy-manifest.json",
        "stripe.config.json",
        "deploy.config.json",
        ".env.example",
    ]

    backed_up = []
    total_size = 0

    for rel_path in files_to_backup:
        src = root / rel_path
        if src.is_file():
            dst = backup_dir / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            backed_up.append(rel_path)
            total_size += src.stat().st_size

    # Backup project metadata
    metadata = {
        "projectId": str(project.id),
        "projectSlug": project.slug,
        "projectName": project.name,
        "framework": project.framework,
        "language": project.language,
        "scanData": project.scan_data,
        "backupId": backup_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    metadata_path = backup_dir / "backup_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    backed_up.append("backup_metadata.json")
    total_size += metadata_path.stat().st_size

    return BackupResult(
        success=len(backed_up) > 0,
        backup_id=backup_id,
        files_backed_up=backed_up,
        size_bytes=total_size,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=f"Backed up {len(backed_up)} file(s)",
    )


def restore_project_backup(project: Project, backup_id: str) -> RecoveryResult:
    """Restore a project from a backup."""
    backup_dir = _get_project_backup_dir(project) / backup_id

    if not backup_dir.exists():
        return RecoveryResult(
            success=False,
            files_restored=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
            message=f"Backup {backup_id} not found",
        )

    root = Path(project.local_path).resolve() if project.local_path else None
    if not root or not root.is_dir():
        return RecoveryResult(
            success=False,
            files_restored=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
            message="Project path not set or invalid",
        )

    restored = []

    # Restore all files except metadata
    for src_file in backup_dir.rglob("*"):
        if src_file.is_file() and src_file.name != "backup_metadata.json":
            rel_path = src_file.relative_to(backup_dir)
            dst = root / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst)
            restored.append(str(rel_path))

    return RecoveryResult(
        success=len(restored) > 0,
        files_restored=restored,
        timestamp=datetime.now(timezone.utc).isoformat(),
        message=f"Restored {len(restored)} file(s)",
    )


def list_project_backups(project: Project) -> list[dict[str, Any]]:
    """List all available backups for a project."""
    backup_dir = _get_project_backup_dir(project)

    if not backup_dir.exists():
        return []

    backups = []
    for backup_path in sorted(backup_dir.iterdir(), reverse=True):
        if backup_path.is_dir():
            metadata_path = backup_path / "backup_metadata.json"
            metadata = {}
            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass

            backups.append({
                "backupId": backup_path.name,
                "timestamp": metadata.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                "files": metadata.get("filesBackedUp", []),
                "size": sum(f.stat().st_size for f in backup_path.rglob("*") if f.is_file()),
            })

    return backups


def cleanup_old_backups(project: Project, keep_days: int = 30) -> dict[str, Any]:
    """Clean up backups older than specified days."""
    backup_dir = _get_project_backup_dir(project)
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)

    if not backup_dir.exists():
        return {"deleted": 0, "kept": 0, "message": "No backups directory"}

    deleted = 0
    kept = 0

    for backup_path in backup_dir.iterdir():
        if backup_path.is_dir():
            metadata_path = backup_path / "backup_metadata.json"
            backup_time = None

            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    backup_time = datetime.fromisoformat(metadata.get("timestamp", ""))
                except (json.JSONDecodeError, ValueError, OSError):
                    pass

            if backup_time and backup_time < cutoff:
                shutil.rmtree(backup_path)
                deleted += 1
            else:
                kept += 1

    return {
        "deleted": deleted,
        "kept": kept,
        "message": f"Cleaned up {deleted} old backup(s), kept {kept}",
    }


def auto_backup_before_critical_operation(project: Project, operation: str) -> BackupResult:
    """Automatically create a backup before critical operations."""
    backup = create_project_backup(project)

    # Log the backup with operation context
    from apps.projects.models import AuditLog

    AuditLog.objects.create(
        project=project,
        actor=None,
        action=f"auto_backup_before_{operation}",
        detail={
            "backupId": backup.backup_id,
            "files": backup.files_backed_up,
            "operation": operation,
        },
    )

    return backup
