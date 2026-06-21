"""Canonical workspace paths for portfolio storefront projects."""

from __future__ import annotations

from pathlib import Path

from apps.projects.models import Project
from apps.stripe_installer.portfolio_catalog import HUB_SLUG, catalog_by_slug, is_stripe_exempt_slug


# Windows dev paths — match Gilliom portfolio repo locations on Ray's machine.
DEFAULT_LOCAL_PATHS: dict[str, str] = {
    "silverfox": r"C:\Software Projects\SilverFox",
    "kistie-store": r"C:\Software Projects\Kristie-Store",
}


def catalog_local_path(slug: str) -> str | None:
    entry = catalog_by_slug(slug)
    if entry and entry.get("defaultLocalPath"):
        return str(entry["defaultLocalPath"]).strip()
    return DEFAULT_LOCAL_PATHS.get(slug)


def is_automation_center_clone_path(path: str) -> bool:
    """True when local_path points at backend/clones/* inside Deployment-Stripe-center."""
    if not path:
        return False
    normalized = path.replace("/", "\\").lower()
    return "deployment-stripe-center" in normalized and "\\clones\\" in normalized


def is_wrong_hub_root_path(project: Project, path: str) -> bool:
    """Portfolio project mistakenly pointed at the Automation Center repo root."""
    if project.slug == HUB_SLUG or not path:
        return False
    normalized = path.replace("/", "\\").lower()
    return normalized.endswith("\\deployment-stripe-center") or normalized.endswith(
        "\\deployment-stripe-center\\"
    )


def should_repair_local_path(project: Project, path: str | None = None) -> bool:
    current = (path if path is not None else project.local_path or "").strip()
    if not current:
        return bool(catalog_local_path(project.slug))
    if is_automation_center_clone_path(current):
        return True
    if is_wrong_hub_root_path(project, current):
        return True
    canonical = catalog_local_path(project.slug)
    if canonical and current != canonical and not Path(current).is_dir() and Path(canonical).is_dir():
        return True
    return False


def repair_portfolio_local_path(project: Project, *, save: bool = True) -> tuple[str, bool]:
    """
    Point portfolio projects at their real repo folder (not hub clones).
    Returns (local_path, changed).
    """
    if project.slug == HUB_SLUG:
        return project.local_path or "", False

    canonical = catalog_local_path(project.slug)
    current = (project.local_path or "").strip()

    if not canonical:
        return current, False

    if not should_repair_local_path(project, current):
        return current, False

    if not Path(canonical).is_dir():
        return current, False

    if save and current != canonical:
        project.local_path = canonical
        project.save(update_fields=["local_path", "updated_at"])
        return canonical, True

    return canonical, current != canonical


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
