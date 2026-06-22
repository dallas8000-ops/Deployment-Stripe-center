"""Canonical workspace paths for portfolio storefront projects."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from apps.projects.models import Project
from apps.stripe_installer.portfolio_catalog import HUB_SLUG, catalog_by_slug, is_stripe_exempt_slug


# Windows dev paths — match portfolio repo locations on Ray's machine.
DEFAULT_LOCAL_PATHS: dict[str, str] = {
    "silverfox": r"C:\Software Projects\SilverFox",
    "kistie-store": r"C:\Software Projects\Kristie-Store",
    "blog-2": r"C:\Software Projects\Blog-2",
    "react-store-catalog": r"C:\Software Projects\React-Store-Catalog",
    "righand": r"C:\Software Projects\RigHand",
    "enpowercommand": r"C:\Software Projects\EnPowerCommand",
    "pc-checker-extreme": r"C:\Software Projects\PC Checker Extreme",
    "dbops-control-center": r"C:\Software Projects\DBOps-Control-Center",
    "elite-fintech-systems": r"C:\Software Projects\Elite Fintech Systems",
    "elite-fintech-web": r"C:\Software Projects\Elite Fintech Systems",
    "specwright": r"C:\Software Projects\Specwright",
}


def catalog_local_path(slug: str) -> str | None:
    entry = catalog_by_slug(slug)
    if entry and entry.get("defaultLocalPath"):
        return str(entry["defaultLocalPath"]).strip()
    return DEFAULT_LOCAL_PATHS.get(slug)


def hub_clone_path(slug: str) -> str:
    root = Path(getattr(settings, "PROJECT_CLONE_ROOT", settings.BASE_DIR / "clones"))
    return str((root / slug).resolve())


def is_automation_center_clone_path(path: str) -> bool:
    """True when local_path points at backend/clones/* inside Deployment-Stripe-center."""
    return is_legacy_hub_clone_path(path) and "deployment-stripe-center" in path.replace("/", "\\").lower()


def is_legacy_hub_clone_path(path: str) -> bool:
    """Stale backend/clones paths from Automation Center or legacy Stripe Installer."""
    if not path:
        return False
    normalized = path.replace("/", "\\").lower()
    if "\\clones\\" not in normalized:
        return False
    return "deployment-stripe-center" in normalized or "stripe installer" in normalized


def is_wrong_hub_root_path(project: Project, path: str) -> bool:
    """Portfolio project mistakenly pointed at the Automation Center repo root."""
    if project.slug == HUB_SLUG or not path:
        return False
    normalized = path.replace("/", "\\").lower()
    return normalized.endswith("\\deployment-stripe-center") or normalized.endswith(
        "\\deployment-stripe-center\\"
    )


def resolve_workspace_path(project: Project) -> str | None:
    """Best local folder: real repo path, existing hub clone, or hub clone target for git."""
    if project.slug == HUB_SLUG:
        return (project.local_path or "").strip() or None

    canonical = catalog_local_path(project.slug)
    if canonical and Path(canonical).is_dir():
        return str(Path(canonical).resolve())

    hub = hub_clone_path(project.slug)
    if Path(hub).is_dir():
        return hub
    if project.git_url:
        return hub
    return canonical


def should_repair_local_path(project: Project, path: str | None = None) -> bool:
    current = (path if path is not None else project.local_path or "").strip()
    target = resolve_workspace_path(project)
    if not target:
        return False
    if not current:
        return True
    if is_legacy_hub_clone_path(current):
        return current != target
    if is_wrong_hub_root_path(project, current):
        return True
    if current != target and Path(target).is_dir() and not Path(current).is_dir():
        return True
    canonical = catalog_local_path(project.slug)
    if canonical and current != canonical and Path(canonical).is_dir():
        if is_legacy_hub_clone_path(current) or not Path(current).is_dir():
            return True
    return False


def repair_portfolio_local_path(project: Project, *, save: bool = True) -> tuple[str, bool]:
    """
    Point portfolio projects at their real repo folder (not legacy hub clones).
    Returns (local_path, changed).
    """
    if project.slug == HUB_SLUG:
        return project.local_path or "", False

    current = (project.local_path or "").strip()
    target = resolve_workspace_path(project)
    if not target or not should_repair_local_path(project, current):
        return current, False

    if save and current != target:
        project.local_path = target
        project.save(update_fields=["local_path", "updated_at"])
        return target, True

    return target, current != target


def ensure_project_workspace(project: Project, *, clone_if_missing: bool = True) -> tuple[str, bool]:
    """Repair stale clone paths and clone from git when the workspace folder is missing."""
    path, changed = repair_portfolio_local_path(project)
    if project.slug == HUB_SLUG:
        return path, changed

    root = Path(project.local_path or path or "")
    if root.is_dir():
        return str(root.resolve()), changed

    if clone_if_missing and project.git_url:
        from apps.projects.git_clone import clone_project_repo

        clone_project_repo(project)
        return project.local_path or "", True

    return project.local_path or path or "", changed


def sync_portfolio_scan_metadata(project: Project, *, save: bool = True) -> None:
    """Ensure productionUrl in scan_data matches portfolio catalog."""
    if not is_stripe_exempt_slug(project.slug) and project.slug != HUB_SLUG:
        return
    entry = catalog_by_slug(project.slug)
    if not entry or not entry.get("productionUrl"):
        return
    scan = dict(project.scan_data or {})
    url = str(entry["productionUrl"]).rstrip("/")
    if scan.get("productionUrl") == url and scan.get("production_url") == url:
        return
    scan["productionUrl"] = url
    scan["production_url"] = url
    project.scan_data = scan
    if save:
        project.save(update_fields=["scan_data", "updated_at"])
