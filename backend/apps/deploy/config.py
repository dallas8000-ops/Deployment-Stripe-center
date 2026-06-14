"""Read/write deploy.config.json in client project repos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps.projects.models import Project

VALID_PLATFORMS = frozenset({"vercel", "railway", "fly", "docker", "unknown"})
VALID_POSTGRES_PROVIDERS = frozenset(
    {"neon", "supabase", "railway", "self-hosted", "unknown"}
)

VALID_ENVIRONMENTS = frozenset({"test", "staging", "production"})

DEFAULT_CONFIG: dict[str, Any] = {
    "productionUrl": "",
    "environments": {
        "test": {"url": ""},
        "staging": {"url": ""},
        "production": {"url": ""},
    },
    "platform": "unknown",
    "postgres": {
        "provider": "neon",
        "connectionEnvVar": "DATABASE_URL",
        "autoProvision": True,
    },
    "monitoring": {"healthCheck": True},
    "backup": {"enabled": True, "retentionDays": 30},
}


def deploy_config_path(root: Path) -> Path:
    return root / "deploy.config.json"


def read_deploy_config(root: Path) -> dict[str, Any]:
    path = deploy_config_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid deploy.config.json: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("deploy.config.json must be a JSON object")
    return raw


def normalize_deploy_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = {**DEFAULT_CONFIG, **raw}
    if "postgres" in raw and isinstance(raw["postgres"], dict):
        config["postgres"] = {**DEFAULT_CONFIG["postgres"], **raw["postgres"]}
    if "monitoring" in raw and isinstance(raw["monitoring"], dict):
        config["monitoring"] = {**DEFAULT_CONFIG["monitoring"], **raw["monitoring"]}
    if "backup" in raw and isinstance(raw["backup"], dict):
        config["backup"] = {**DEFAULT_CONFIG["backup"], **raw["backup"]}
    if "environments" in raw and isinstance(raw["environments"], dict):
        merged_envs = dict(DEFAULT_CONFIG["environments"])
        for name, entry in raw["environments"].items():
            if name not in VALID_ENVIRONMENTS:
                continue
            if isinstance(entry, dict):
                merged_envs[name] = {
                    **DEFAULT_CONFIG["environments"][name],
                    **entry,
                    "url": str(entry.get("url") or "").rstrip("/"),
                }
        config["environments"] = merged_envs

    platform = str(config.get("platform") or "unknown")
    if platform == "render":
        platform = "unknown"
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Invalid platform: {platform}")
    config["platform"] = platform

    postgres = config.get("postgres") or {}
    provider = str(postgres.get("provider") or "neon")
    if provider == "render":
        provider = "neon"
    if provider not in VALID_POSTGRES_PROVIDERS:
        raise ValueError(f"Invalid postgres.provider: {provider}")
    config["postgres"] = {**DEFAULT_CONFIG["postgres"], **postgres, "provider": provider}

    domain = config.get("domain")
    production_url = str(config.get("productionUrl") or "").rstrip("/")
    if not production_url and domain:
        production_url = f"https://{str(domain).strip('/')}"
    config["productionUrl"] = production_url
    return config


def write_deploy_config(root: Path, config: dict[str, Any]) -> Path:
    normalized = normalize_deploy_config(config)
    path = deploy_config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    return path


def config_from_project(project: Project, root: Path | None = None) -> dict[str, Any]:
    scan = project.scan_data or {}
    base = dict(DEFAULT_CONFIG)
    base["productionUrl"] = str(scan.get("productionUrl") or scan.get("production_url") or "").rstrip("/")
    base["platform"] = str(scan.get("deployPlatform") or "unknown")

    if root and root.is_dir():
        try:
            on_disk = read_deploy_config(root)
            if on_disk:
                return normalize_deploy_config({**base, **on_disk})
        except ValueError:
            pass
    return normalize_deploy_config(base)


def sync_project_from_config(project: Project, config: dict[str, Any]) -> None:
    scan = dict(project.scan_data or {})
    production_url = str(config.get("productionUrl") or "").rstrip("/")
    if production_url:
        scan["productionUrl"] = production_url
    platform = config.get("platform")
    if platform and platform != "unknown":
        scan["deployPlatform"] = platform
    project.scan_data = scan
    project.save(update_fields=["scan_data", "updated_at"])


def _url_from_deploy_config(cfg: dict[str, Any], active_env: str) -> str:
    envs = cfg.get("environments") or {}
    if isinstance(envs, dict) and active_env in envs:
        entry = envs.get(active_env) or {}
        if isinstance(entry, dict):
            env_url = str(entry.get("url") or "").rstrip("/")
            if env_url:
                return env_url
    url = str(cfg.get("productionUrl") or "").rstrip("/")
    if not url and cfg.get("domain"):
        url = f"https://{str(cfg['domain']).strip('/')}"
    return url


def resolve_production_url(project: Project, root: Path | None, fallback: str = "") -> str:
    active_env = project.active_environment

    if root and root.is_dir():
        try:
            cfg = normalize_deploy_config(read_deploy_config(root))
            url = _url_from_deploy_config(cfg, active_env)
            if url:
                return url
        except ValueError:
            pass

    scan = project.scan_data or {}
    url = str(scan.get("productionUrl") or scan.get("production_url") or "").rstrip("/")
    return url or fallback.rstrip("/")
