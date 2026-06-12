"""Stripe health diagnostics — port of diagnostics.ts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import stripe

from apps.projects.models import Project
from apps.stripe_engine.codegen.generator import generate_all
from apps.stripe_engine.provision import load_manifest
from apps.stripe_engine.verify import verify_stripe_keys
from apps.vault.models import get_secret, list_secret_keys

_BACKEND_FRAMEWORKS = ("django", "flask", "rails", "laravel")
_FRONTEND_FRAMEWORKS = ("react", "vue", "angular", "svelte", "preact")
_REAL_ENV_FILES = (".env.local", ".env", ".env.development", ".env.development.local")


@dataclass
class StripeIssue:
    id: str
    category: str
    severity: str  # error | warning | info
    title: str
    message: str
    fix_hint: str
    auto_fixable: bool = False
    fix_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiagnosticReport:
    scanned_at: str
    project_name: str
    health_score: int
    issues: list[StripeIssue]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scannedAt": self.scanned_at,
            "projectName": self.project_name,
            "healthScore": self.health_score,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
        }


def score_issues(issues: list[StripeIssue]) -> int:
    if not issues:
        return 100
    weights = {"error": 0.0, "warning": 0.5, "info": 0.85}
    total = sum(weights.get(i.severity, 0) for i in issues)
    return round((total / len(issues)) * 100)


def _push(issues: list[StripeIssue], issue: StripeIssue) -> None:
    if not any(i.id == issue.id for i in issues):
        issues.append(issue)


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


def _env_has_key(project_root: Path, env_file: str, key: str) -> bool:
    path = project_root / env_file
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return any(line.startswith(f"{key}=") and len(line) > len(key) + 1 for line in content.splitlines())
    except OSError:
        return False


def _resolve_env_file(project_root: Path, candidate_files: list[str]) -> str:
    """Return the first real (non-example) env file that actually exists on disk."""
    return next(
        (f for f in _REAL_ENV_FILES if f in candidate_files and _file_exists(project_root / f)),
        ".env.local",
    )


# ---------------------------------------------------------------------------
# Individual check helpers — each adds zero or one issue to the list
# ---------------------------------------------------------------------------

def _check_security(issues: list[StripeIssue], scan: dict, project_root: Path) -> None:
    detected_secrets = scan.get("detected_secrets") or []
    if detected_secrets:
        _push(issues, StripeIssue(
            id="secrets-in-files", category="security", severity="error",
            title="Secrets exposed in project files",
            message=f"{len(detected_secrets)} API key(s) found in source or env files",
            fix_hint="Store in vault and remove from tracked files",
        ))

    if ".env" not in _read_gitignore(project_root):
        _push(issues, StripeIssue(
            id="gitignore-env", category="security", severity="error",
            title=".env files not gitignored",
            message=".env and .env.local may be committed to git",
            fix_hint="Add .env* patterns to .gitignore",
            auto_fixable=True, fix_action="fix-gitignore",
        ))


def _check_npm_packages(issues: list[StripeIssue], project: Project, scan: dict) -> None:
    if not scan.get("existing_stripe_code"):
        return
    if project.framework in _BACKEND_FRAMEWORKS:
        return

    all_deps = set(scan.get("dependencies") or []) | set(scan.get("dev_dependencies") or [])
    if project.framework in _FRONTEND_FRAMEWORKS:
        if "@stripe/stripe-js" not in all_deps and "@stripe/react-stripe-js" not in all_deps:
            _push(issues, StripeIssue(
                id="missing-stripe-package", category="packages", severity="warning",
                title="Stripe.js package not installed",
                message="Stripe code detected but @stripe/stripe-js is missing from package.json",
                fix_hint="Run: npm install @stripe/stripe-js @stripe/react-stripe-js",
            ))
    elif "stripe" not in all_deps:
        _push(issues, StripeIssue(
            id="missing-stripe-package", category="packages", severity="error",
            title="stripe npm package missing",
            message="Stripe code detected but stripe is not in package.json",
            fix_hint="Run: npm install stripe",
        ))


def _check_config_and_files(
    issues: list[StripeIssue], project: Project, project_root: Path, scan: dict, manifest: dict | None
) -> None:
    if not _file_exists(project_root / "stripe.config.json"):
        _push(issues, StripeIssue(
            id="missing-stripe-config", category="config", severity="warning",
            title="stripe.config.json missing",
            message="No pricing/webhook configuration file found",
            fix_hint="Create from defaults",
            auto_fixable=True, fix_action="create-stripe-config",
        ))

    if not scan.get("suggested_features"):
        return

    expected_files = list(generate_all(project.framework, manifest).keys())
    missing = [
        f for f in expected_files
        if f not in (".env.example",) and not f.startswith("docs/")
        and not _file_exists(project_root / f)
    ]
    if missing:
        critical = [f for f in missing if any(k in f for k in ("webhook", "stripe", "checkout"))]
        _push(issues, StripeIssue(
            id="missing-integration-files", category="files",
            severity="error" if critical else "warning",
            title="Missing Stripe integration files",
            message=f"{len(missing)} expected file(s) not found (e.g. {', '.join(missing[:2])})",
            fix_hint="Generate boilerplate integration code",
            auto_fixable=True, fix_action="generate-files",
        ))


def _check_vault_keys(issues: list[StripeIssue], project: Project, vault_keys: list[str]) -> None:
    for key in ("STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY"):
        if key not in vault_keys:
            _push(issues, StripeIssue(
                id=f"vault-missing-{key.lower()}", category="credentials", severity="error",
                title=f"{key} not in vault",
                message="Required Stripe credential missing from encrypted vault",
                fix_hint="Store key in vault",
            ))

    if (
        project.framework == "nextjs"
        and "STRIPE_PUBLISHABLE_KEY" in vault_keys
        and "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY" not in vault_keys
    ):
        _push(issues, StripeIssue(
            id="missing-public-env-key", category="credentials", severity="warning",
            title="NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY missing",
            message="Client-side checkout needs the public key in NEXT_PUBLIC_* env var",
            fix_hint="Sync publishable key",
            auto_fixable=True, fix_action="sync-public-key",
        ))


def _check_key_validity(issues: list[StripeIssue], verification: Any, secret: str | None, publishable: str | None) -> None:
    if secret and not verification.secret_key.valid:
        _push(issues, StripeIssue(
            id="invalid-secret-key", category="credentials", severity="error",
            title="Stripe secret key invalid",
            message=verification.secret_key.message,
            fix_hint="Update STRIPE_SECRET_KEY in vault",
        ))

    if publishable and not verification.publishable_key.valid:
        _push(issues, StripeIssue(
            id="invalid-publishable-key", category="credentials", severity="error",
            title="Stripe publishable key invalid",
            message=verification.publishable_key.message,
            fix_hint="Ensure pk matches secret key mode",
        ))

    if (
        verification.secret_key.valid
        and verification.publishable_key.valid
        and verification.secret_key.mode != verification.publishable_key.mode
    ):
        _push(issues, StripeIssue(
            id="key-mode-mismatch", category="credentials", severity="error",
            title="Test/live key mode mismatch",
            message=f"Secret is {verification.secret_key.mode}, publishable is {verification.publishable_key.mode}",
            fix_hint="Use matching test or live key pairs",
        ))


def _check_env_sync(
    issues: list[StripeIssue], project_root: Path, scan: dict, vault_keys: list[str]
) -> None:
    if not any(k.startswith("STRIPE_") for k in vault_keys):
        return
    if "STRIPE_SECRET_KEY" not in vault_keys:
        return

    # Skip .example files — they hold placeholders, not live secrets
    env_file = _resolve_env_file(project_root, scan.get("env_files") or [])
    if _file_exists(project_root / env_file) and not _env_has_key(project_root, env_file, "STRIPE_SECRET_KEY"):
        _push(issues, StripeIssue(
            id="env-out-of-sync", category="credentials", severity="warning",
            title=".env.local out of sync with vault",
            message=f"Keys in vault but missing from {env_file}",
            fix_hint="Sync vault secrets to .env.local",
            auto_fixable=True, fix_action="sync-env",
        ))


def _check_catalog(issues: list[StripeIssue], manifest: dict | None, secret: str) -> None:
    if not manifest or not manifest.get("prices"):
        _push(issues, StripeIssue(
            id="no-catalog-manifest", category="catalog", severity="warning",
            title="No Stripe product catalog",
            message="No prices provisioned — checkout may fail",
            fix_hint="Run provision to create products and prices",
            auto_fixable=True, fix_action="provision-stripe",
        ))
        return

    stripe.api_key = secret
    for price in manifest.get("prices", []):
        try:
            p = stripe.Price.retrieve(price["id"])
            if not p.active:
                _push(issues, StripeIssue(
                    id=f"price-inactive-{price['id']}", category="catalog", severity="error",
                    title=f"Price inactive: {price.get('tier', price['id'])}",
                    message=f"Price {price['id']} is archived in Stripe",
                    fix_hint="Re-run provision",
                    auto_fixable=True, fix_action="provision-stripe",
                ))
        except stripe.error.StripeError:
            _push(issues, StripeIssue(
                id=f"price-missing-{price['id']}", category="catalog", severity="error",
                title=f"Price not found: {price.get('tier', price['id'])}",
                message=f"Manifest references {price['id']} but it does not exist in Stripe",
                fix_hint="Re-provision catalog",
                auto_fixable=True, fix_action="provision-stripe",
            ))


def _check_webhook(issues: list[StripeIssue], manifest: dict | None, secret: str, scan: dict) -> None:
    webhook = (manifest or {}).get("webhookEndpoint")
    if webhook and webhook.get("id"):
        stripe.api_key = secret
        try:
            endpoint = stripe.WebhookEndpoint.retrieve(webhook["id"])
            if endpoint.status != "enabled":
                _push(issues, StripeIssue(
                    id="webhook-disabled", category="webhooks", severity="error",
                    title="Webhook endpoint disabled",
                    message=f"Endpoint {webhook.get('url')} is disabled in Stripe",
                    fix_hint="Re-provision webhook",
                    auto_fixable=True, fix_action="provision-stripe",
                ))
        except stripe.error.StripeError:
            _push(issues, StripeIssue(
                id="webhook-endpoint-missing", category="webhooks", severity="error",
                title="Registered webhook not found",
                message="Manifest webhook ID no longer exists in Stripe account",
                fix_hint="Re-register webhook endpoint",
                auto_fixable=True, fix_action="provision-stripe",
            ))
    elif "webhooks" in (scan.get("suggested_features") or []):
        _push(issues, StripeIssue(
            id="webhook-not-registered", category="webhooks", severity="warning",
            title="No webhook endpoint registered",
            message="Stripe cannot deliver events without a registered endpoint",
            fix_hint="Provision webhook with your app URL",
            auto_fixable=True, fix_action="provision-stripe",
        ))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_diagnostics(project: Project, project_root: Path) -> DiagnosticReport:
    issues: list[StripeIssue] = []
    scan = project.scan_data or {}
    manifest = load_manifest(project_root)

    _check_security(issues, scan, project_root)
    _check_npm_packages(issues, project, scan)
    _check_config_and_files(issues, project, project_root, scan, manifest)

    vault_keys = list_secret_keys(project)
    _check_vault_keys(issues, project, vault_keys)

    secret = get_secret(project, "STRIPE_SECRET_KEY")
    publishable = get_secret(project, "STRIPE_PUBLISHABLE_KEY")
    verification = verify_stripe_keys(secret, publishable)

    _check_key_validity(issues, verification, secret, publishable)
    _check_env_sync(issues, project_root, scan, vault_keys)

    if "STRIPE_WEBHOOK_SECRET" not in vault_keys:
        _push(issues, StripeIssue(
            id="missing-webhook-secret", category="webhooks", severity="warning",
            title="STRIPE_WEBHOOK_SECRET not configured",
            message="Webhook handler cannot verify Stripe signatures without whsec_",
            fix_hint="Provision webhook via pipeline",
            auto_fixable=True, fix_action="provision-stripe",
        ))

    if verification.secret_key.valid and secret:
        _check_catalog(issues, manifest, secret)
        _check_webhook(issues, manifest, secret, scan)

    health_score = score_issues(issues)
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")
    fixable = sum(1 for i in issues if i.auto_fixable)

    summary = (
        "Stripe setup looks healthy — no issues detected."
        if not issues
        else f"Found {len(issues)} issue(s): {errors} error(s), {warnings} warning(s). {fixable} auto-fixable."
    )

    return DiagnosticReport(
        scanned_at=datetime.now(timezone.utc).isoformat(),
        project_name=project.name,
        health_score=health_score,
        issues=issues,
        summary=summary,
    )
