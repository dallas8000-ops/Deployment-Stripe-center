"""Production readiness checks — port of deploy/readiness.ts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.projects.models import Project
from apps.stripe_installer.provision import load_manifest
from apps.stripe_installer.verify import verify_stripe_keys
from apps.vault.models import get_secret

_DB_PREFIXES = ("postgres://", "postgresql://", "sqlite://", "sqlite+")
# Env files that are always gitignored — secrets there are not committed leaks
_SAFE_ENV_FILES = {
    ".env.local", ".env", ".env.development.local",
    ".env.test.local", ".env.production.local",
}


@dataclass
class ReadinessCheck:
    id: str
    category: str
    name: str
    status: str  # pass | warn | fail
    message: str
    fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_readiness(checks: list[ReadinessCheck]) -> int:
    if not checks:
        return 0
    weights = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    total = sum(weights.get(c.status, 0) for c in checks)
    return round((total / len(checks)) * 100)


def readiness_label(score: int) -> str:
    if score >= 80:
        return "Production ready"
    if score >= 50:
        return "Almost ready"
    return "Not ready"


def _file_exists(path: Path) -> bool:
    return path.is_file()


def _read_gitignore(project_root: Path) -> str:
    path = project_root / ".gitignore"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _head_reachable(url: str, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        req = Request(url, method="HEAD")
        with urlopen(req, timeout=timeout) as resp:
            status = resp.status
            return status < 500, f"HTTP {status}"
    except HTTPError as exc:
        # 4xx = server is reachable, just rejecting this specific request
        return exc.code < 500, f"HTTP {exc.code}"
    except URLError as exc:
        return False, str(exc.reason if hasattr(exc, "reason") else exc)
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Individual check helpers
# ---------------------------------------------------------------------------

def _stripe_key_checks(project: Project) -> list[ReadinessCheck]:
    secret = get_secret(project, "STRIPE_SECRET_KEY")
    publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
    v = verify_stripe_keys(secret, publishable)
    webhook_secret = get_secret(project, "STRIPE_WEBHOOK_SECRET")
    return [
        ReadinessCheck(
            id="stripe-secret", category="stripe", name="Stripe secret key",
            status="pass" if v.secret_key.valid else "fail",
            message=v.secret_key.message,
            fix="Store STRIPE_SECRET_KEY in vault",
        ),
        ReadinessCheck(
            id="stripe-live-mode", category="stripe", name="Production Stripe keys",
            status="pass" if v.secret_key.mode == "live" else "warn",
            message="Using live mode keys" if v.secret_key.mode == "live"
                    else f"Using {v.secret_key.mode} mode — switch to live for production",
            fix="Replace sk_test_ with sk_live_ keys in vault",
        ),
        ReadinessCheck(
            id="stripe-publishable", category="stripe", name="Stripe publishable key",
            status="pass" if v.publishable_key.valid else "warn",
            message=v.publishable_key.message,
            fix="Store STRIPE_PUBLISHABLE_KEY in vault",
        ),
        ReadinessCheck(
            id="stripe-webhook-secret", category="stripe", name="Webhook signing secret",
            status="pass" if webhook_secret else "warn",
            message="Configured" if webhook_secret else "STRIPE_WEBHOOK_SECRET missing",
            fix="Run pipeline with provision enabled",
        ),
    ]


def _stripe_manifest_check(project_root: Path) -> ReadinessCheck:
    manifest = load_manifest(project_root)
    price_count = len(manifest.get("prices", [])) if manifest else 0
    return ReadinessCheck(
        id="stripe-manifest", category="stripe", name="Stripe catalog manifest",
        status="pass" if price_count > 0 else "warn",
        message=f"{price_count} price(s) configured" if price_count else "No prices in manifest",
        fix="Run full setup with provision",
    )


def _database_checks(project: Project, project_root: Path) -> list[ReadinessCheck]:
    db_url = get_secret(project, "DATABASE_URL")
    db_valid = bool(db_url and db_url.startswith(_DB_PREFIXES))
    return [
        ReadinessCheck(
            id="db-url", category="database", name="DATABASE_URL configured",
            status="pass" if db_valid else "warn",
            message=f"Database URL set ({db_url.split('://')[0]})" if db_valid else "DATABASE_URL missing or invalid",
            fix="Store DATABASE_URL in vault (postgresql://... or sqlite://...)",
        ),
        ReadinessCheck(
            id="db-schema", category="database", name="Database schema file",
            status="pass" if _file_exists(project_root / "db" / "schema.sql") else "warn",
            message="db/schema.sql exists" if _file_exists(project_root / "db" / "schema.sql") else "Schema not generated",
            fix="Run full setup with generate enabled",
        ),
    ]


def _ssl_checks(prod_url: str | None) -> list[ReadinessCheck]:
    if prod_url and str(prod_url).startswith("https://"):
        ok, msg = _head_reachable(str(prod_url))
        return [
            ReadinessCheck(
                id="ssl-https", category="ssl", name="HTTPS production URL",
                status="pass", message="Production URL uses HTTPS",
            ),
            ReadinessCheck(
                id="ssl-reachable", category="ssl", name="Production site reachable",
                status="pass" if ok else "warn",
                message=msg if ok else f"Site not reachable yet ({msg})",
                fix="Deploy app, then re-run readiness",
            ),
        ]
    return [
        ReadinessCheck(
            id="ssl-https", category="ssl", name="HTTPS enabled",
            status="warn", message="SSL auto-provisioned by host on deploy",
            fix="Deploy with HTTPS URL",
        ),
    ]


def _security_checks(project_root: Path, scan: dict) -> list[ReadinessCheck]:
    gitignore = _read_gitignore(project_root)
    detected = scan.get("detected_secrets") or []
    committed = [s for s in detected if (s.get("file") or "").split("/")[-1] not in _SAFE_ENV_FILES]
    return [
        ReadinessCheck(
            id="gitignore-env", category="security", name=".env files gitignored",
            status="pass" if ".env" in gitignore else "fail",
            message=".env in .gitignore" if ".env" in gitignore else ".env may be committed!",
            fix="Add .env, .env.local, .stripe-installer/ to .gitignore",
        ),
        ReadinessCheck(
            id="no-committed-secrets", category="security", name="No secrets in tracked files",
            status="pass" if not committed else "fail",
            message="No secrets detected in tracked files" if not committed
                    else f"{len(committed)} secret(s) found in tracked files",
            fix="Move secrets to vault; use .env.example with placeholders only",
        ),
    ]


def _deploy_checks(project: Project, project_root: Path, scan: dict) -> list[ReadinessCheck]:
    has_health = any(
        _file_exists(project_root / p)
        for p in ("app/api/health/route.ts", "pages/api/health.ts", "stripe/views.py")
    )
    has_backup = (
        _file_exists(project_root / "scripts" / "backup-db.sh")
        or _file_exists(project_root / "scripts" / "backup-db.ps1")
    )
    platform = scan.get("deployPlatform") or ("django" if project.framework == "django" else "unknown")
    has_build = (
        scan.get("has_package_json", False)
        or _file_exists(project_root / "package.json")
        or project.framework == "django"
    )

    checks = [
        ReadinessCheck(
            id="health-endpoint", category="monitoring", name="Health check endpoint",
            status="pass" if has_health else "warn",
            message="/api/health or stripe module exists" if has_health else "Health endpoint not found",
            fix="Generate integration files or run generate-infra",
        ),
        ReadinessCheck(
            id="backup-script", category="backup", name="Database backup script",
            status="pass" if has_backup else "warn",
            message="Backup scripts exist" if has_backup else "No backup script",
            fix="Run generate-infra from Deploy panel or scripts/backup-db.sh",
        ),
        ReadinessCheck(
            id="deploy-platform", category="deploy", name="Deployment platform",
            status="pass" if platform != "unknown" else "warn",
            message=f"Detected: {platform}" if platform != "unknown" else "Platform not detected",
            fix="Run scan after adding deploy config",
        ),
        ReadinessCheck(
            id="build-script", category="deploy", name="Build script available",
            status="pass" if has_build else "warn",
            message="package.json or Django project" if has_build else "No build configuration",
        ),
    ]
    if project.framework != "unknown":
        checks.append(ReadinessCheck(
            id="framework-detected", category="deploy", name="Framework detected",
            status="pass", message=f"{project.framework} ({project.language})",
        ))
    return checks


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_readiness_checks(
    project: Project,
    project_root: Path,
    *,
    production_url: str | None = None,
) -> list[ReadinessCheck]:
    scan = project.scan_data or {}
    prod_url = production_url or scan.get("productionUrl") or scan.get("appUrl")

    checks: list[ReadinessCheck] = []
    checks.extend(_stripe_key_checks(project))
    checks.append(_stripe_manifest_check(project_root))
    checks.extend(_database_checks(project, project_root))
    checks.append(ReadinessCheck(
        id="domain-configured", category="domain", name="Production URL configured",
        status="pass" if prod_url else "warn",
        message=str(prod_url) if prod_url else "No production URL configured",
        fix="Set productionUrl in project scan data or pass app_url",
    ))
    checks.extend(_ssl_checks(prod_url))
    checks.extend(_security_checks(project_root, scan))
    checks.extend(_deploy_checks(project, project_root, scan))
    return checks
