"""Comprehensive health monitoring and alerting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from apps.projects.models import Project
from apps.stripe_engine.diagnostics import run_diagnostics
from apps.stripe_engine.drift import detect_drift
from apps.stripe_engine.webhook_health import webhook_health
from apps.vault.models import get_secret


@dataclass
class HealthMetric:
    """Individual health metric."""
    name: str
    status: str  # healthy, warning, critical, unknown
    value: Any
    threshold: Any
    message: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
            "timestamp": self.timestamp,
        }


@dataclass
class HealthReport:
    """Comprehensive health report for a project."""
    project_id: str
    project_slug: str
    overall_status: str  # healthy, warning, critical, unknown
    metrics: list[HealthMetric]
    alerts: list[dict[str, Any]]
    timestamp: str
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectId": str(self.project_id),
            "projectSlug": self.project_slug,
            "overallStatus": self.overall_status,
            "metrics": [m.to_dict() for m in self.metrics],
            "alerts": self.alerts,
            "timestamp": self.timestamp,
            "score": self.score,
        }


def _check_vault_health(project: Project) -> HealthMetric:
    """Check vault configuration health."""
    from apps.vault.models import list_secret_keys

    try:
        keys = list_secret_keys(project)
        required_keys = ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY"]
        missing = [k for k in required_keys if k not in keys]

        if missing:
            return HealthMetric(
                name="vault_configuration",
                status="critical",
                value={"configuredKeys": len(keys), "missingKeys": missing},
                threshold={"requiredKeys": required_keys},
                message=f"Missing required keys: {', '.join(missing)}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        return HealthMetric(
            name="vault_configuration",
            status="healthy",
            value={"configuredKeys": len(keys)},
            threshold={"minRequiredKeys": len(required_keys)},
            message="Vault properly configured",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        return HealthMetric(
            name="vault_configuration",
            status="unknown",
            value={"error": str(exc)},
            threshold={},
            message=f"Unable to check vault: {str(exc)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def _check_stripe_api_health(project: Project) -> HealthMetric:
    """Check Stripe API connectivity."""
    try:
        secret = get_secret(project, "STRIPE_SECRET_KEY")
        if not secret:
            return HealthMetric(
                name="stripe_api_connectivity",
                status="critical",
                value=None,
                threshold={},
                message="STRIPE_SECRET_KEY not configured",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        import stripe
        stripe.api_key = secret
        account = stripe.Account.retrieve()

        return HealthMetric(
            name="stripe_api_connectivity",
            status="healthy",
            value={"accountId": account.id, "country": account.country},
            threshold={},
            message="Stripe API accessible",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        return HealthMetric(
            name="stripe_api_connectivity",
            status="critical",
            value={"error": str(exc)},
            threshold={},
            message=f"Stripe API error: {str(exc)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def _check_diagnostics_health(project: Project) -> HealthMetric:
    """Check diagnostics health."""
    from pathlib import Path

    try:
        root = Path(project.local_path).resolve() if project.local_path else None
        if not root or not root.is_dir():
            return HealthMetric(
                name="diagnostics",
                status="unknown",
                value=None,
                threshold={},
                message="Project path not set",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        report = run_diagnostics(project, root)
        error_count = sum(1 for i in report.issues if i.severity == "error")
        warning_count = sum(1 for i in report.issues if i.severity == "warning")

        if error_count > 0:
            return HealthMetric(
                name="diagnostics",
                status="critical",
                value={"errorCount": error_count, "warningCount": warning_count, "healthScore": report.health_score},
                threshold={"maxErrors": 0},
                message=f"{error_count} error(s) detected",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        elif warning_count > 3:
            return HealthMetric(
                name="diagnostics",
                status="warning",
                value={"errorCount": error_count, "warningCount": warning_count, "healthScore": report.health_score},
                threshold={"maxWarnings": 3},
                message=f"{warning_count} warning(s) detected",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        return HealthMetric(
            name="diagnostics",
            status="healthy",
            value={"errorCount": error_count, "warningCount": warning_count, "healthScore": report.health_score},
            threshold={"maxErrors": 0, "maxWarnings": 3},
            message="No critical issues",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        return HealthMetric(
            name="diagnostics",
            status="unknown",
            value={"error": str(exc)},
            threshold={},
            message=f"Unable to run diagnostics: {str(exc)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def _check_drift_health(project: Project) -> HealthMetric:
    """Check drift health."""
    try:
        result = detect_drift(project)
        drift_count = result.get("driftCount", 0)

        if drift_count > 5:
            return HealthMetric(
                name="configuration_drift",
                status="critical",
                value={"driftCount": drift_count},
                threshold={"maxDrift": 5},
                message=f"{drift_count} drift item(s) detected",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        elif drift_count > 0:
            return HealthMetric(
                name="configuration_drift",
                status="warning",
                value={"driftCount": drift_count},
                threshold={"maxDrift": 0},
                message=f"{drift_count} drift item(s) detected",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        return HealthMetric(
            name="configuration_drift",
            status="healthy",
            value={"driftCount": drift_count},
            threshold={"maxDrift": 0},
            message="No configuration drift",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except RuntimeError as exc:
        return HealthMetric(
            name="configuration_drift",
            status="unknown",
            value={"error": str(exc)},
            threshold={},
            message=f"Unable to check drift: {str(exc)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def _check_webhook_health(project: Project) -> HealthMetric:
    """Check webhook health."""
    try:
        result = webhook_health(project)

        if not result.get("healthy"):
            issue_count = len(result.get("issues", []))
            return HealthMetric(
                name="webhook_health",
                status="critical" if issue_count > 0 else "warning",
                value={"healthy": False, "issueCount": issue_count},
                threshold={"healthy": True},
                message=f"{issue_count} webhook issue(s) detected",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        return HealthMetric(
            name="webhook_health",
            status="healthy",
            value={"healthy": True, "endpointCount": len(result.get("endpoints", []))},
            threshold={"healthy": True},
            message="Webhooks healthy",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        return HealthMetric(
            name="webhook_health",
            status="unknown",
            value={"error": str(exc)},
            threshold={},
            message=f"Unable to check webhook health: {str(exc)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def _calculate_overall_status(metrics: list[HealthMetric]) -> tuple[str, int]:
    """Calculate overall status and score from metrics."""
    if not metrics:
        return "unknown", 0

    status_weights = {"critical": 0, "warning": 50, "healthy": 100, "unknown": 0}
    statuses = [m.status for m in metrics]

    # If any critical, overall is critical
    if "critical" in statuses:
        return "critical", 0

    # If any warning, overall is warning
    if "warning" in statuses:
        return "warning", 50

    # If any unknown, overall is warning
    if "unknown" in statuses:
        return "warning", 75

    # All healthy
    return "healthy", 100


def _generate_alerts(metrics: list[HealthMetric]) -> list[dict[str, Any]]:
    """Generate alerts from metrics."""
    alerts = []
    for metric in metrics:
        if metric.status in ("critical", "warning"):
            alerts.append({
                "metric": metric.name,
                "severity": metric.status,
                "message": metric.message,
                "value": metric.value,
                "timestamp": metric.timestamp,
            })
    return alerts


def run_health_monitor(project: Project) -> HealthReport:
    """Run comprehensive health monitoring on a project."""
    metrics = [
        _check_vault_health(project),
        _check_stripe_api_health(project),
        _check_diagnostics_health(project),
        _check_drift_health(project),
        _check_webhook_health(project),
    ]

    overall_status, score = _calculate_overall_status(metrics)
    alerts = _generate_alerts(metrics)

    return HealthReport(
        project_id=project.id,
        project_slug=project.slug,
        overall_status=overall_status,
        metrics=metrics,
        alerts=alerts,
        timestamp=datetime.now(timezone.utc).isoformat(),
        score=score,
    )


def run_all_projects_health_monitor() -> dict[str, Any]:
    """Run health monitoring on all projects."""
    from apps.vault.models import VaultSecret

    project_ids = (
        VaultSecret.objects.filter(key_name="STRIPE_SECRET_KEY")
        .values_list("project_id", flat=True)
        .distinct()
    )

    reports = []
    healthy_count = 0
    warning_count = 0
    critical_count = 0

    for pid in project_ids:
        try:
            project = Project.objects.get(id=pid)
            report = run_health_monitor(project)
            reports.append(report.to_dict())

            if report.overall_status == "healthy":
                healthy_count += 1
            elif report.overall_status == "warning":
                warning_count += 1
            elif report.overall_status == "critical":
                critical_count += 1
        except Project.DoesNotExist:
            continue

    return {
        "summary": {
            "total": len(reports),
            "healthy": healthy_count,
            "warning": warning_count,
            "critical": critical_count,
        },
        "reports": reports,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
