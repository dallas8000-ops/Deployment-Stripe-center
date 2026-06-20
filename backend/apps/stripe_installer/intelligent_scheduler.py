"""Intelligent scheduling and optimization for automated tasks."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from apps.projects.models import Project
from apps.runs.models import PipelineRun


@dataclass
class ScheduleRecommendation:
    """Recommendation for optimal scheduling."""
    task_type: str
    recommended_time: str
    reason: str
    expected_benefit: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskType": self.task_type,
            "recommendedTime": self.recommended_time,
            "reason": self.reason,
            "expectedBenefit": self.expected_benefit,
            "confidence": self.confidence,
        }


def _analyze_project_activity_patterns(project: Project) -> dict[str, Any]:
    """Analyze historical activity patterns for a project."""
    runs = PipelineRun.objects.filter(project=project).order_by("-created_at")[:50]

    if not runs:
        return {"hasHistory": False}

    # Analyze time patterns
    hour_counts = defaultdict(int)
    day_counts = defaultdict(int)
    success_rates = defaultdict(list)

    for run in runs:
        if run.created_at:
            hour_counts[run.created_at.hour] += 1
            day_counts[run.created_at.weekday()] += 1
            success_rates[run.created_at.hour].append(run.status == PipelineRun.Status.COMPLETED)

    # Calculate success rate per hour
    hourly_success_rates = {}
    for hour, statuses in success_rates.items():
        if statuses:
            hourly_success_rates[hour] = sum(statuses) / len(statuses)

    # Find peak activity times
    peak_hour = max(hour_counts.items(), key=lambda x: x[1])[0] if hour_counts else 0
    peak_day = max(day_counts.items(), key=lambda x: x[1])[0] if day_counts else 0

    # Find best success rate hour
    best_hour = max(hourly_success_rates.items(), key=lambda x: x[1])[0] if hourly_success_rates else peak_hour

    return {
        "hasHistory": True,
        "peakHour": peak_hour,
        "peakDay": peak_day,
        "bestSuccessHour": best_hour,
        "hourlySuccessRates": hourly_success_rates,
        "totalRuns": len(runs),
    }


def _get_optimal_schedule_time(patterns: dict[str, Any], task_type: str) -> ScheduleRecommendation:
    """Determine optimal schedule time based on patterns and task type."""
    if not patterns.get("hasHistory"):
        # Default recommendations for new projects
        defaults = {
            "pipeline_run": ScheduleRecommendation(
                task_type="pipeline_run",
                recommended_time="02:00 UTC",
                reason="Low traffic period for new projects",
                expected_benefit="Minimizes impact on development",
                confidence=0.5,
            ),
            "drift_check": ScheduleRecommendation(
                task_type="drift_check",
                recommended_time="00:00 UTC",
                reason="Daily baseline check",
                expected_benefit="Early detection of configuration issues",
                confidence=0.6,
            ),
            "health_monitor": ScheduleRecommendation(
                task_type="health_monitor",
                recommended_time="*/30 minutes",
                reason="Continuous monitoring",
                expected_benefit="Rapid issue detection",
                confidence=0.8,
            ),
        }
        return defaults.get(task_type, defaults["pipeline_run"])

    # Intelligent scheduling based on patterns
    best_hour = patterns.get("bestSuccessHour", 0)
    peak_hour = patterns.get("peakHour", 0)

    if task_type == "pipeline_run":
        # Schedule during low activity but high success rate
        optimal_hour = (best_hour + 12) % 24  # Opposite of best success hour to avoid conflicts
        return ScheduleRecommendation(
            task_type="pipeline_run",
            recommended_time=f"{optimal_hour:02d}:00 UTC",
            reason=f"Scheduled away from peak activity (hour {peak_hour}) but aligned with success patterns",
            expected_benefit="Optimizes for success rate while minimizing conflicts",
            confidence=0.8,
        )

    elif task_type == "drift_check":
        # Schedule during quiet period
        optimal_hour = (peak_hour + 6) % 24  # 6 hours after peak
        return ScheduleRecommendation(
            task_type="drift_check",
            recommended_time=f"{optimal_hour:02d}:00 UTC",
            reason=f"Scheduled 6 hours after peak activity (hour {peak_hour})",
            expected_benefit="Checks configuration when changes are likely settled",
            confidence=0.7,
        )

    elif task_type == "health_monitor":
        return ScheduleRecommendation(
            task_type="health_monitor",
            recommended_time="*/30 minutes",
            reason="Continuous monitoring regardless of patterns",
            expected_benefit="Real-time health visibility",
            confidence=0.9,
        )

    return ScheduleRecommendation(
        task_type=task_type,
        recommended_time="02:00 UTC",
        reason="Default scheduling",
        expected_benefit="Standard maintenance window",
        confidence=0.5,
    )


def get_schedule_recommendations(project: Project) -> list[ScheduleRecommendation]:
    """Get intelligent schedule recommendations for a project."""
    patterns = _analyze_project_activity_patterns(project)

    task_types = ["pipeline_run", "drift_check", "health_monitor", "auto_heal"]
    recommendations = []

    for task_type in task_types:
        rec = _get_optimal_schedule_time(patterns, task_type)
        recommendations.append(rec)

    return recommendations


def optimize_celery_schedule(project: Project) -> dict[str, Any]:
    """Generate optimized Celery beat schedule for a project."""
    recommendations = get_schedule_recommendations(project)

    optimized_schedule = {}
    for rec in recommendations:
        if rec.task_type == "pipeline_run":
            optimized_schedule["run-pipeline"] = {
                "task": "runs.execute_pipeline",
                "schedule": f"crontab(hour={rec.recommended_time.split(':')[0]}, minute=0)",
                "reason": rec.reason,
            }
        elif rec.task_type == "drift_check":
            optimized_schedule["check-drift"] = {
                "task": "stripe_engine.check_project_drift",
                "schedule": f"crontab(hour={rec.recommended_time.split(':')[0]}, minute=0)",
                "reason": rec.reason,
            }
        elif rec.task_type == "health_monitor":
            optimized_schedule["health-monitor"] = {
                "task": "stripe_engine.health_monitor_all_projects",
                "schedule": "crontab(minute='*/30')",
                "reason": rec.reason,
            }
        elif rec.task_type == "auto_heal":
            optimized_schedule["auto-heal"] = {
                "task": "stripe_engine.auto_heal_project",
                "schedule": f"crontab(hour={(int(rec.recommended_time.split(':')[0]) + 2) % 24}, minute=0)",
                "reason": rec.reason,
            }

    return {
        "projectId": str(project.id),
        "projectSlug": project.slug,
        "optimizedSchedule": optimized_schedule,
        "recommendations": [r.to_dict() for r in recommendations],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_global_optimization_recommendations() -> dict[str, Any]:
    """Get global optimization recommendations across all projects."""
    from apps.vault.models import VaultSecret

    project_ids = (
        VaultSecret.objects.filter(key_name="STRIPE_SECRET_KEY")
        .values_list("project_id", flat=True)
        .distinct()
    )

    all_patterns = []
    for pid in project_ids:
        try:
            project = Project.objects.get(id=pid)
            patterns = _analyze_project_activity_patterns(project)
            all_patterns.append({
                "projectId": str(project.id),
                "projectSlug": project.slug,
                "patterns": patterns,
            })
        except Project.DoesNotExist:
            continue

    # Aggregate patterns
    if not all_patterns:
        return {"hasData": False, "recommendation": "Insufficient data for global optimization"}

    total_runs = sum(p["patterns"].get("totalRuns", 0) for p in all_patterns if p["patterns"].get("hasHistory"))

    # Find common patterns
    peak_hours = [p["patterns"].get("peakHour") for p in all_patterns if p["patterns"].get("hasHistory")]
    if peak_hours:
        avg_peak_hour = sum(peak_hours) / len(peak_hours)
    else:
        avg_peak_hour = 14  # Default to 2 PM

    return {
        "hasData": True,
        "totalProjects": len(all_patterns),
        "totalRuns": total_runs,
        "averagePeakHour": avg_peak_hour,
        "recommendation": {
            "globalHealthMonitor": "*/30 minutes",
            "globalDriftCheck": f"crontab(hour={int(avg_peak_hour + 6) % 24}, minute=0)",
            "globalAutoHeal": f"crontab(hour={int(avg_peak_hour + 12) % 24}, minute=30)",
            "reason": f"Based on average peak activity at hour {int(avg_peak_hour)}",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
