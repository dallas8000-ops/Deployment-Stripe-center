"""Canonical workspace paths for portfolio storefront projects."""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings

from apps.projects.models import Project
from apps.stripe_core.portfolio_catalog import HUB_SLUG, catalog_by_slug, catalog_live_urls


# Windows dev paths — match portfolio repo locations on Ray's machine.
DEFAULT_LOCAL_PATHS: dict[str, str] = {
    "agripay-logistics-ai": r"C:\Software Projects\AgriPay Logistics AI",
    "silverfox": r"C:\Software Projects\SilverFox",
    "kistie-store": r"C:\Software Projects\Kristie-Store",
    "blog-2": r"C:\Software Projects\Blog-2",
    "react-store-catalog": r"C:\Software Projects\React-Store-Catalog",
    "righand": r"C:\Software Projects\RigHand",
    "enpowercommand": r"C:\Software Projects\EnPowerCommand",
    "pc-checker-extreme": r"C:\Software Projects\PC Checker Extreme",
    "dbops-control-center": r"C:\Software Projects\DBOps-Control-Center",
    "elite-fintech-systems": r"C:\Software Projects\Elite Fintech Systems",
    "specwright": r"C:\Software Projects\Specwright",
    "eastbridge-ops": r"C:\Software Projects\EastBridge Ops Intelligence",
}

HUB_REPO_ROOT = Path(settings.REPO_ROOT).resolve()


def resolve_scan_root(local_path: str | Path) -> Path:
    """
    Django monorepos (e.g. apps/backend/manage.py) — scan the API package, not the web root.
    Keeps local_path on the git repo root; only filesystem detection uses this path.
    """
    root = Path(local_path).resolve()
    for candidate in (root / "apps" / "backend", root / "backend", root):
        if (candidate / "manage.py").is_file():
            return candidate
    return root


def relative_scan_root(repo_root: Path, scan_root: Path) -> str:
    if scan_root.resolve() == repo_root.resolve():
        return ""
    try:
        return str(scan_root.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return ""


def catalog_local_path(slug: str) -> str | None:
    entry = catalog_by_slug(slug)
    if entry and entry.get("defaultLocalPath"):
        return str(entry["defaultLocalPath"]).strip()
    return DEFAULT_LOCAL_PATHS.get(slug)


def is_inside_hub_repo(path: str, project: Project | None = None) -> bool:
    """True when path is inside the Automation Center repo (never valid for portfolio apps)."""
    if project and project.slug == HUB_SLUG:
        return False
    if not path:
        return False
    try:
        resolved = Path(path).resolve()
        resolved.relative_to(HUB_REPO_ROOT)
        return True
    except (ValueError, OSError):
        return False


def is_invalid_portfolio_path(project: Project, path: str) -> bool:
    """Portfolio projects must use their own repo folder — never a path inside this hub."""
    if project.slug == HUB_SLUG or not path:
        return False
    if is_legacy_hub_clone_path(path):
        return True
    return is_inside_hub_repo(path, project)


def is_automation_center_nested_path(path: str) -> bool:
    """UI helper — path points inside Deployment-Stripe-center (not the user's app repo)."""
    return is_inside_hub_repo(path)


def is_legacy_hub_clone_path(path: str) -> bool:
    """Stale backend/clones paths from older Automation Center builds."""
    if not path:
        return False
    normalized = path.replace("/", "\\").lower()
    return "\\clones\\" in normalized or (
        "\\clone" in normalized and "deployment-stripe-center" in normalized
    )


def _valid_local_path(project: Project) -> str:
    current = (project.local_path or "").strip()
    if current and not is_invalid_portfolio_path(project, current):
        return current
    return ""


def resolve_workspace_path(project: Project) -> str | None:
    """Real repo folder from catalog or Settings — never inside this hub."""
    if project.slug == HUB_SLUG:
        return (project.local_path or "").strip() or str(HUB_REPO_ROOT)

    canonical = catalog_local_path(project.slug)
    explicit = _valid_local_path(project)

    if canonical and Path(canonical).is_dir():
        return str(Path(canonical).resolve())
    if explicit and Path(explicit).is_dir():
        return str(Path(explicit).resolve())
    if canonical and not is_inside_hub_repo(canonical):
        return canonical
    if explicit:
        return explicit
    return None


def workspace_path_error(project: Project, path: str | None = None) -> str | None:
    target = (path or project.local_path or "").strip()
    if not target:
        return "Set local_path to your real project folder (e.g. C:\\Software Projects\\YourApp)."
    if is_legacy_hub_clone_path(target):
        return (
            "local_path cannot use backend/clones inside this hub. "
            "Use your app's own folder on disk (clone the repo there manually if needed)."
        )
    if is_invalid_portfolio_path(project, target):
        return (
            "local_path cannot be inside the Automation Center repository. "
            "Use your app's own folder on disk."
        )
    return None


def should_repair_local_path(project: Project, path: str | None = None) -> bool:
    current = (path if path is not None else project.local_path or "").strip()
    if current and is_invalid_portfolio_path(project, current):
        return True
    target = resolve_workspace_path(project)
    if not target:
        return False
    if not current:
        return True
    if current != target and Path(target).is_dir() and not Path(current).is_dir():
        return True
    canonical = catalog_local_path(project.slug)
    if canonical and current != canonical and Path(canonical).is_dir():
        if is_invalid_portfolio_path(project, current) or not Path(current).is_dir():
            return True
    return False


def repair_portfolio_local_path(project: Project, *, save: bool = True) -> tuple[str, bool]:
    """Point portfolio projects at their real repo folder. Returns (local_path, changed)."""
    if project.slug == HUB_SLUG:
        return project.local_path or "", False

    current = (project.local_path or "").strip()
    if current and is_invalid_portfolio_path(project, current) and not resolve_workspace_path(project):
        if save:
            project.local_path = ""
            project.save(update_fields=["local_path", "updated_at"])
        return "", True

    target = resolve_workspace_path(project)
    if not target or not should_repair_local_path(project, current):
        return current, False

    if save and current != target:
        project.local_path = target
        project.save(update_fields=["local_path", "updated_at"])
        return target, True

    return target, current != target


def require_project_folder(project: Project) -> Path:
    """Resolved, existing project root — raises if missing or inside the hub repo."""
    repair_portfolio_local_path(project)
    err = workspace_path_error(project)
    if err:
        raise ValueError(err)
    root = Path(resolve_workspace_path(project) or project.local_path or "")
    if not root.is_dir():
        raise FileNotFoundError(
            f"Project folder not found: {root}. Open that folder in your editor and clone the repo there manually."
        )
    return root.resolve()


def ensure_project_workspace(project: Project) -> tuple[str, bool]:
    """Repair invalid paths and verify the real project folder exists. Never clones or copies repos."""
    path, changed = repair_portfolio_local_path(project)
    if project.slug == HUB_SLUG:
        return path or str(HUB_REPO_ROOT), changed
    require_project_folder(project)
    return project.local_path or path or "", changed


def reconcile_hub_workspace(project: Project) -> tuple[str, bool]:
    """Repair local_path and delete stale hub clone dirs when a bad path is detected."""
    before = (project.local_path or "").strip()
    was_invalid = bool(before and is_invalid_portfolio_path(project, before))
    path, changed = repair_portfolio_local_path(project)
    if was_invalid:
        remove_stale_hub_workspaces()
    return path, changed


def remove_stale_hub_workspaces() -> list[str]:
    """Delete any legacy workspace folders created inside backend/ (clones, cloneN, etc.)."""
    removed: list[str] = []
    backend = Path(settings.BASE_DIR)
    candidates: list[Path] = []
    clones = backend / "clones"
    if clones.exists():
        candidates.append(clones)
    for path in backend.glob("clone*"):
        if path.is_dir() and path not in candidates:
            candidates.append(path)
    for path in candidates:
        shutil.rmtree(path, ignore_errors=True)
        removed.append(str(path))
    return removed


def reconcile_all_portfolio_workspaces() -> dict[str, list[str]]:
    """Repair every non-hub project and delete legacy backend/clones folders."""
    from apps.projects.models import Project

    repaired: list[str] = []
    for project in Project.objects.exclude(slug=HUB_SLUG):
        before = (project.local_path or "").strip()
        _, changed = reconcile_hub_workspace(project)
        if changed or (before and is_invalid_portfolio_path(project, before)):
            repaired.append(project.slug)
    removed = remove_stale_hub_workspaces()
    return {"repaired": repaired, "removed": removed}


def sync_portfolio_scan_metadata(project: Project, *, save: bool = True) -> None:
    """Ensure productionUrl / webhookPath in scan_data matches portfolio catalog."""
    entry = catalog_by_slug(project.slug or "")
    if not entry:
        return
    scan = dict(project.scan_data or {})
    changed = False
    url = str(entry.get("productionUrl") or "").rstrip("/")
    if url and scan.get("productionUrl") != url:
        scan["productionUrl"] = url
        scan["production_url"] = url
        changed = True
    live = catalog_live_urls(entry)
    for key, scan_key in (
        ("webUrl", "webProductionUrl"),
        ("demoUrl", "demoUrl"),
        ("portfolioDemoUrl", "portfolioDemoUrl"),
    ):
        val = live.get(key) or ""
        if val and scan.get(scan_key) != val:
            scan[scan_key] = val
            changed = True
    webhook = str(entry.get("webhookPath") or "").strip()
    if webhook and scan.get("webhookPath") != webhook:
        scan["webhookPath"] = webhook
        changed = True
    if changed:
        project.scan_data = scan
        if save:
            project.save(update_fields=["scan_data", "updated_at"])
