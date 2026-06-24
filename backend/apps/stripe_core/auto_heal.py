"""Automated self-healing system — auto-fix common issues without manual intervention."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.projects.models import Project
from apps.diagnostics.diagnostics import DiagnosticReport, run_diagnostics
from apps.stripe_core.repair import RepairResult, run_auto_fix, run_repair_action


@dataclass
class HealPolicy:
    """Policy for when to auto-heal issues."""
    severity_threshold: str = "warning"  # Only auto-fix warnings and info by default
    max_auto_fixes_per_run: int = 5
    require_confirmation_for: list[str] = None  # Issue IDs that always require confirmation
    safe_actions: list[str] = None  # Actions that are always safe to run automatically

    def __post_init__(self):
        if self.require_confirmation_for is None:
            self.require_confirmation_for = []
        if self.safe_actions is None:
            self.safe_actions = [
                "fix-gitignore",
                "sync-public-key",
                "sync-env",
                "create-stripe-config",
            ]


@dataclass
class HealResult:
    """Result of an auto-healing operation."""
    success: bool
    issues_detected: int
    issues_auto_fixed: int
    issues_skipped: int
    repairs: list[RepairResult]
    timestamp: str
    policy_applied: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "issuesDetected": self.issues_detected,
            "issuesAutoFixed": self.issues_auto_fixed,
            "issuesSkipped": self.issues_skipped,
            "repairs": [r.to_dict() for r in self.repairs],
            "timestamp": self.timestamp,
            "policyApplied": self.policy_applied,
        }


def _should_auto_fix(issue_id: str, severity: str, fix_action: str | None, policy: HealPolicy) -> bool:
    """Determine if an issue should be auto-fixed based on policy."""
    # Skip if severity is below threshold
    severity_order = {"error": 0, "warning": 1, "info": 2}
    if severity_order.get(severity, 0) < severity_order.get(policy.severity_threshold, 1):
        return False

    # Skip if issue requires confirmation
    if issue_id in policy.require_confirmation_for:
        return False

    # Skip if no fix action available
    if not fix_action:
        return False

    # Allow if action is in safe list
    if fix_action in policy.safe_actions:
        return True

    # For other actions, only allow if severity is info (lowest risk)
    return severity == "info"


def run_auto_heal(
    project: Project,
    *,
    policy: HealPolicy | None = None,
    dry_run: bool = False,
    app_url: str = "http://localhost:8000",
) -> HealResult:
    """Run automated self-healing on a project."""
    policy = policy or HealPolicy()
    root = Path(project.local_path).resolve() if project.local_path else None

    if not root or not root.is_dir():
        return HealResult(
            success=False,
            issues_detected=0,
            issues_auto_fixed=0,
            issues_skipped=0,
            repairs=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
            policy_applied=policy.__dict__,
        )

    # Run diagnostics to find issues
    report = run_diagnostics(project, root)
    issues = report.issues

    # Filter issues based on policy
    target_issues = []
    for issue in issues:
        if _should_auto_fix(issue.id, issue.severity, issue.fix_action, policy):
            target_issues.append(issue)

    # Limit number of auto-fixes per run
    target_issues = target_issues[: policy.max_auto_fixes_per_run]

    if dry_run:
        # Return what would be fixed without actually fixing
        return HealResult(
            success=True,
            issues_detected=len(issues),
            issues_auto_fixed=len(target_issues),
            issues_skipped=len(issues) - len(target_issues),
            repairs=[
                RepairResult(
                    action=issue.fix_action or "unknown",
                    success=True,
                    message=f"[DRY RUN] Would fix: {issue.title}",
                )
                for issue in target_issues
            ],
            timestamp=datetime.now(timezone.utc).isoformat(),
            policy_applied=policy.__dict__,
        )

    # Run auto-fix
    repairs, new_report = run_auto_fix(
        project,
        issue_ids=[i.id for i in target_issues],
        force=True,
        app_url=app_url,
    )

    # Count successful fixes
    successful_fixes = sum(1 for r in repairs if r.success)

    return HealResult(
        success=successful_fixes > 0,
        issues_detected=len(issues),
        issues_auto_fixed=successful_fixes,
        issues_skipped=len(issues) - len(target_issues),
        repairs=repairs,
        timestamp=datetime.now(timezone.utc).isoformat(),
        policy_applied=policy.__dict__,
    )


def run_auto_heal_with_drift(
    project: Project,
    *,
    policy: HealPolicy | None = None,
    app_url: str = "http://localhost:8000",
) -> HealResult:
    """Run auto-healing triggered by drift detection."""
    from apps.diagnostics.drift import detect_drift

    policy = policy or HealPolicy()

    # Check for drift first
    try:
        drift_result = detect_drift(project)
        if drift_result["driftCount"] == 0:
            # No drift, no need to heal
            return HealResult(
                success=True,
                issues_detected=0,
                issues_auto_fixed=0,
                issues_skipped=0,
                repairs=[],
                timestamp=datetime.now(timezone.utc).isoformat(),
                policy_applied=policy.__dict__,
            )
    except RuntimeError:
        # Drift detection failed, proceed with diagnostics anyway
        pass

    # Run auto-heal
    return run_auto_heal(project, policy=policy, dry_run=False, app_url=app_url)


def get_heal_recommendations(project: Project) -> list[dict[str, Any]]:
    """Get recommendations for what can be auto-healed without actually fixing."""
    root = Path(project.local_path).resolve() if project.local_path else None
    if not root or not root.is_dir():
        return []

    report = run_diagnostics(project, root)
    policy = HealPolicy()

    recommendations = []
    for issue in report.issues:
        if _should_auto_fix(issue.id, issue.severity, issue.fix_action, policy):
            recommendations.append(
                {
                    "issueId": issue.id,
                    "title": issue.title,
                    "severity": issue.severity,
                    "fixAction": issue.fix_action,
                    "message": issue.message,
                    "autoFixable": True,
                }
            )

    return recommendations
