"""Predictive AI for issue prevention and optimization."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from apps.ai_assistant.chat import chat_with_ai
from apps.ai_assistant.services import _assert_safe
from apps.projects.models import Project
from apps.diagnostics.diagnostics import DiagnosticReport, run_diagnostics
from apps.diagnostics.drift import detect_drift
from apps.stripe_core.readiness import ReadinessCheck, run_readiness_checks


@dataclass
class PredictionResult:
    """Result of a predictive analysis."""
    risk_level: str  # low, medium, high
    predicted_issues: list[dict[str, Any]]
    optimization_recommendations: list[dict[str, Any]]
    confidence_score: float
    timestamp: str
    automation_plan: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "riskLevel": self.risk_level,
            "predictedIssues": self.predicted_issues,
            "optimizationRecommendations": self.optimization_recommendations,
            "confidenceScore": self.confidence_score,
            "timestamp": self.timestamp,
        }
        if self.automation_plan is not None:
            payload["automationPlan"] = self.automation_plan
        return payload


@dataclass
class AutomationAction:
    """Single automation candidate in the decision plan."""

    action: str
    title: str
    automation_mode: str  # auto, gated, manual
    priority_score: float
    confidence: float
    risk_level: str
    rationale: str
    prerequisites: list[str]
    source_signals: list[str]
    expected_outcome: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "title": self.title,
            "automationMode": self.automation_mode,
            "priorityScore": round(self.priority_score, 2),
            "confidence": round(self.confidence, 2),
            "riskLevel": self.risk_level,
            "rationale": self.rationale,
            "prerequisites": self.prerequisites,
            "sourceSignals": self.source_signals,
            "expectedOutcome": self.expected_outcome,
        }


@dataclass
class AutomationPlan:
    """Ranked automation plan generated from multiple signals."""

    autonomy_score: float
    recommended_mode: str
    actions: list[AutomationAction]
    blocked_actions: list[str]
    summary: str
    signal_coverage: float
    confidence_score: float
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "autonomyScore": round(self.autonomy_score, 2),
            "recommendedMode": self.recommended_mode,
            "actions": [action.to_dict() for action in self.actions],
            "blockedActions": self.blocked_actions,
            "summary": self.summary,
            "signalCoverage": round(self.signal_coverage, 2),
            "confidenceScore": round(self.confidence_score, 2),
            "timestamp": self.timestamp,
        }


def _analyze_historical_patterns(project: Project) -> dict[str, Any]:
    """Analyze historical data for patterns."""
    scan = project.scan_data or {}
    drift = scan.get("lastDrift") or {}
    audit_logs = list(project.audit_logs.all()[:20])

    # Count common issues from drift
    drift_items = drift.get("items") or []
    issue_categories = Counter([item.get("category") for item in drift_items])
    issue_severities = Counter([item.get("severity") for item in drift_items])

    # Analyze audit patterns
    action_patterns = Counter([log.action for log in audit_logs])

    return {
        "driftIssueCategories": dict(issue_categories),
        "driftIssueSeverities": dict(issue_severities),
        "actionPatterns": dict(action_patterns),
        "driftCount": drift.get("driftCount", 0),
        "lastDriftCheck": drift.get("checkedAt"),
        "recentFailureSignals": sum(1 for item in drift_items if item.get("severity") == "error"),
        "recentWarningSignals": sum(1 for item in drift_items if item.get("severity") == "warning"),
    }


def _calculate_risk_score(patterns: dict[str, Any]) -> tuple[str, float]:
    """Calculate risk score based on patterns."""
    drift_count = patterns.get("driftCount", 0)
    severities = patterns.get("driftIssueSeverities", {})

    # Weight different severity levels
    error_count = severities.get("error", 0)
    warning_count = severities.get("warning", 0)
    info_count = severities.get("info", 0)

    # Calculate weighted score
    weighted_score = (error_count * 3.0) + (warning_count * 1.5) + (info_count * 0.5)

    # Normalize to 0-1 range
    max_possible = 10.0  # Assume 10 as reasonable max
    normalized = min(weighted_score / max_possible, 1.0)

    # Determine risk level
    if normalized >= 0.7:
        return "high", normalized
    elif normalized >= 0.4:
        return "medium", normalized
    else:
        return "low", normalized


def _calculate_autonomy_score(patterns: dict[str, Any], diagnostics: Any, readiness: list[Any]) -> float:
    """Estimate how much of the workflow can be safely automated."""
    total_checks = len(getattr(diagnostics, "issues", []) or []) + len(readiness)
    if total_checks == 0:
        return 0.35

    auto_fixable = sum(1 for issue in getattr(diagnostics, "issues", []) if getattr(issue, "auto_fixable", False))
    pass_checks = sum(1 for check in readiness if getattr(check, "status", None) == "pass")
    drift_count = int(patterns.get("driftCount", 0) or 0)
    error_count = int(patterns.get("recentFailureSignals", 0) or 0)

    automation_ratio = (auto_fixable + pass_checks) / total_checks
    stability_bonus = 0.2 if drift_count == 0 and error_count == 0 else 0.0
    penalty = min(0.4, (drift_count * 0.03) + (error_count * 0.05))

    score = automation_ratio + stability_bonus - penalty
    return max(0.05, min(score, 0.95))


def _generate_ai_predictions(project: Project, patterns: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Use AI to generate predictions and recommendations."""
    context = {
        "project": project.name,
        "framework": project.framework,
        "language": project.language,
        "patterns": patterns,
    }

    prompt = (
        "You are a predictive AI assistant for Stripe integrations. "
        "Analyze the historical patterns and predict potential issues. "
        "Also suggest optimizations. "
        "Return ONLY JSON with two arrays: predictedIssues and optimizationRecommendations.\n\n"
        f"Context: {json.dumps(context, indent=2)}\n\n"
        "Format: {\"predictedIssues\": [{\"type\", \"description\", \"probability\", \"severity\", \"preventiveAction\"}], "
        "\"optimizationRecommendations\": [{\"area\", \"description\", \"expectedBenefit\", \"complexity\"}]}"
    )

    try:
        text, provider = chat_with_ai(project, prompt, max_tokens=2000)
        data = json.loads(text)
        return data.get("predictedIssues", []), data.get("optimizationRecommendations", [])
    except Exception:
        # Fallback to rule-based predictions
        return _generate_rule_based_predictions(patterns)


def _collect_automation_context(project: Project) -> dict[str, Any]:
    """Collect the signals needed for a more autonomous decision engine."""
    root = Path(project.local_path).resolve() if project.local_path else None

    try:
        diagnostics = run_diagnostics(project, root) if root and root.is_dir() else None
    except Exception:
        diagnostics = None

    try:
        from apps.deploy.postgres import get_production_url

        prod_url = get_production_url(project, "")
        readiness = run_readiness_checks(project, root, production_url=prod_url) if root and root.is_dir() else []
    except Exception:
        readiness = []

    patterns = _analyze_historical_patterns(project)
    risk_level, confidence = _calculate_risk_score(patterns)
    autonomy_score = _calculate_autonomy_score(patterns, diagnostics, readiness)

    return {
        "root": root,
        "diagnostics": diagnostics,
        "readiness": readiness,
        "patterns": patterns,
        "risk_level": risk_level,
        "confidence": confidence,
        "autonomy_score": autonomy_score,
    }


def _build_automation_actions(project: Project, context: dict[str, Any]) -> AutomationPlan:
    """Build a ranked automation plan from all available signals."""
    diagnostics = context.get("diagnostics")
    readiness = context.get("readiness") or []
    patterns = context.get("patterns") or {}

    actions: list[AutomationAction] = []
    blocked_actions: list[str] = []

    if diagnostics:
        for issue in diagnostics.issues:
            if getattr(issue, "auto_fixable", False) and getattr(issue, "fix_action", None):
                severity = getattr(issue, "severity", "warning")
                confidence = 0.92 if severity == "error" else 0.82 if severity == "warning" else 0.72
                priority_score = (100 if severity == "error" else 70 if severity == "warning" else 45) + (15 if issue.fix_action in {"fix-gitignore", "sync-env", "create-stripe-config"} else 0)
                actions.append(
                    AutomationAction(
                        action=issue.fix_action,
                        title=issue.title,
                        automation_mode="auto" if severity in ("error", "warning") else "gated",
                        priority_score=priority_score,
                        confidence=confidence,
                        risk_level=severity,
                        rationale=issue.fix_hint,
                        prerequisites=["project-local-path"],
                        source_signals=["diagnostics", issue.category],
                        expected_outcome="Reduce immediate operational risk",
                    )
                )
            elif getattr(issue, "fix_action", None):
                blocked_actions.append(issue.fix_action)

    drift_count = int(patterns.get("driftCount", 0) or 0)
    if drift_count > 0:
        actions.append(
            AutomationAction(
                action="run-drift-heal",
                title="Repair configuration drift",
                automation_mode="gated" if drift_count > 5 else "auto",
                priority_score=95 if drift_count > 5 else 88,
                confidence=min(0.95, 0.55 + drift_count * 0.08),
                risk_level="high" if drift_count > 5 else "medium",
                rationale="Historical drift indicates the project will keep regressing without automated repair.",
                prerequisites=["vault-secrets", "local-project-path"],
                source_signals=["drift", "historical-patterns"],
                expected_outcome="Stabilize the project state and prevent configuration decay",
            )
        )

    if any(check.status == "fail" for check in readiness):
        actions.append(
            AutomationAction(
                action="remediate-readiness-gaps",
                title="Close readiness failures",
                automation_mode="gated",
                priority_score=84,
                confidence=0.74,
                risk_level="medium",
                rationale="Readiness checks show the deployment path is not yet safe to fully automate.",
                prerequisites=["review-failed-checks"],
                source_signals=["readiness"],
                expected_outcome="Raise deployability and lower release risk",
            )
        )

    if patterns.get("actionPatterns", {}).get("clone_repo", 0) > 5:
        actions.append(
            AutomationAction(
                action="optimize-git-cache",
                title="Reduce repeated cloning overhead",
                automation_mode="auto",
                priority_score=60,
                confidence=0.7,
                risk_level="low",
                rationale="Frequent cloning suggests repeated cold-start work that can be optimized away.",
                prerequisites=["pipeline-control"],
                source_signals=["audit-patterns"],
                expected_outcome="Faster pipeline execution and fewer redundant operations",
            )
        )

    if not actions:
        actions.append(
            AutomationAction(
                action="monitor-only",
                title="Continue passive monitoring",
                automation_mode="manual",
                priority_score=10,
                confidence=0.5,
                risk_level="low",
                rationale="Signals are stable enough that the safest decision is to keep observing.",
                prerequisites=[],
                source_signals=["baseline"],
                expected_outcome="Preserve current state while collecting more data",
            )
        )

    actions.sort(key=lambda item: (item.priority_score, item.confidence), reverse=True)

    autonomy_score = float(context.get("autonomy_score", 0.35))
    recommended_mode = "full-auto" if autonomy_score >= 0.8 else "semi-auto" if autonomy_score >= 0.55 else "manual"
    blocked_text = sorted(set(blocked_actions))
    summary = (
        f"{len(actions)} ranked automation action(s) derived from diagnostics, drift, readiness, and historical patterns. "
        f"Recommended mode: {recommended_mode}."
    )

    confidence_score = float(context.get("confidence", 0.5))
    signal_coverage = min(1.0, (1.0 if diagnostics else 0.0) + (1.0 if readiness else 0.0) + (1.0 if patterns else 0.0)) / 3.0

    return AutomationPlan(
        autonomy_score=autonomy_score,
        recommended_mode=recommended_mode,
        actions=actions[:8],
        blocked_actions=blocked_text,
        summary=summary,
        signal_coverage=signal_coverage,
        confidence_score=confidence_score,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def get_autonomous_automation_plan(
    project: Project,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a high-level plan that is as close to hands-off automation as possible."""
    context = context or _collect_automation_context(project)
    plan = _build_automation_actions(project, context)

    prompt_context = {
        "project": project.name,
        "framework": project.framework,
        "language": project.language,
        "riskLevel": context["risk_level"],
        "confidence": context["confidence"],
        "autonomyScore": context["autonomy_score"],
        "actions": [a.to_dict() for a in plan.actions],
    }

    ai_summary = None
    try:
        text, _provider = chat_with_ai(
            project,
            "You are an automation strategist for Stripe integrations. "
            "Given the plan context, return only JSON with keys executiveSummary, nextBestAction, and escalationBoundary.\n\n"
            f"Context: {json.dumps(prompt_context, indent=2)}",
            max_tokens=800,
        )
        ai_summary = json.loads(text)
    except Exception:
        ai_summary = None

    payload = plan.to_dict()
    if ai_summary:
        payload["aiSummary"] = ai_summary
    return payload


def _generate_rule_based_predictions(patterns: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Generate predictions based on rules when AI is unavailable."""
    predicted_issues = []
    recommendations = []

    drift_count = patterns.get("driftCount", 0)
    severities = patterns.get("driftIssueSeverities", {})

    # Rule-based predictions
    if severities.get("error", 0) > 0:
        predicted_issues.append({
            "type": "configuration_drift",
            "description": "Configuration drift detected - may cause webhook failures",
            "probability": "high",
            "severity": "high",
            "preventiveAction": "Run auto-heal or manually fix configuration issues",
        })

    if drift_count > 3:
        predicted_issues.append({
            "type": "frequent_drift",
            "description": "Frequent drift detected - consider automating configuration sync",
            "probability": "medium",
            "severity": "medium",
            "preventiveAction": "Enable automated drift detection and healing",
        })

    # Optimization recommendations
    if patterns.get("actionPatterns", {}).get("clone_repo", 0) > 5:
        recommendations.append({
            "area": "git_operations",
            "description": "Frequent repo cloning - consider using persistent volumes or caching",
            "expectedBenefit": "Faster pipeline execution",
            "complexity": "low",
        })

    recommendations.append({
        "area": "monitoring",
        "description": "Enable automated health checks and alerting",
        "expectedBenefit": "Early issue detection",
        "complexity": "low",
    })

    return predicted_issues, recommendations


def run_predictive_analysis(project: Project) -> PredictionResult:
    """Run predictive analysis on a project."""
    context = _collect_automation_context(project)
    patterns = context["patterns"]
    risk_level, confidence = context["risk_level"], context["confidence"]

    # Try AI predictions first, fall back to rule-based
    try:
        predicted_issues, recommendations = _generate_ai_predictions(project, patterns)
    except Exception:
        predicted_issues, recommendations = _generate_rule_based_predictions(patterns)

    return PredictionResult(
        risk_level=risk_level,
        predicted_issues=predicted_issues,
        optimization_recommendations=recommendations,
        confidence_score=confidence,
        timestamp=datetime.now(timezone.utc).isoformat(),
        automation_plan=get_autonomous_automation_plan(project, context),
    )


def get_proactive_recommendations(project: Project) -> dict[str, Any]:
    """Get proactive recommendations based on current state and predictions."""
    root = Path(project.local_path).resolve() if project.local_path else None
    if not root or not root.is_dir():
        return {"recommendations": [], "reason": "Project path not set"}

    predictions = run_predictive_analysis(project)
    automation_plan = predictions.automation_plan or get_autonomous_automation_plan(project)

    recommendations = []
    for action in automation_plan.get("actions", []):
        recommendations.append({
            "source": "automation-plan",
            "type": action.get("automationMode", "manual"),
            "title": action.get("title"),
            "action": action.get("action"),
            "priority": "high" if action.get("priorityScore", 0) >= 80 else "medium" if action.get("priorityScore", 0) >= 55 else "low",
            "confidence": action.get("confidence", 0),
            "automationMode": action.get("automationMode"),
            "sourceSignals": action.get("sourceSignals", []),
        })

    return {
        "recommendations": recommendations[:10],
        "riskLevel": predictions.risk_level,
        "confidenceScore": predictions.confidence_score,
        "automationMode": automation_plan.get("recommendedMode", "manual"),
        "automationPlan": automation_plan,
        "timestamp": predictions.timestamp,
    }
