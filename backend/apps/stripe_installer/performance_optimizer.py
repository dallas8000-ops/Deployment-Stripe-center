"""Automated performance optimization recommendations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps.projects.models import Project
from apps.diagnostics.diagnostics import run_diagnostics
from apps.stripe_installer.readiness import run_readiness_checks


@dataclass
class OptimizationRecommendation:
    """Performance optimization recommendation."""
    area: str
    title: str
    description: str
    impact: str  # high, medium, low
    effort: str  # high, medium, low
    actionable_steps: list[str]
    estimated_improvement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "area": self.area,
            "title": self.title,
            "description": self.description,
            "impact": self.impact,
            "effort": self.effort,
            "actionableSteps": self.actionable_steps,
            "estimatedImprovement": self.estimated_improvement,
        }


def _analyze_webhook_performance(project: Project) -> list[OptimizationRecommendation]:
    """Analyze webhook performance and provide recommendations."""
    recommendations = []

    # Check webhook endpoint configuration
    from apps.diagnostics.webhook_health import webhook_health

    try:
        health = webhook_health(project)
        endpoints = health.get("endpoints", [])

        if len(endpoints) > 3:
            recommendations.append(OptimizationRecommendation(
                area="webhooks",
                title="Reduce webhook endpoint count",
                description=f"Project has {len(endpoints)} webhook endpoints registered",
                impact="medium",
                effort="low",
                actionable_steps=[
                    "Review and remove unused webhook endpoints",
                    "Consolidate similar endpoints if possible",
                    "Use a single endpoint with event filtering",
                ],
                estimated_improvement="Reduced latency and simpler management",
            ))

        recent_events = health.get("recentEventTypes", {})
        if recent_events:
            total_events = sum(recent_events.values())
            if total_events > 1000:
                recommendations.append(OptimizationRecommendation(
                    area="webhooks",
                    title="Optimize webhook event filtering",
                    description=f"High volume of webhook events detected ({total_events} recent events)",
                    impact="high",
                    effort="medium",
                    actionable_steps=[
                        "Review enabled event types and disable unnecessary ones",
                        "Implement event filtering in webhook handler",
                        "Consider using Stripe CLI for local development",
                    ],
                    estimated_improvement="Reduced processing load and faster response times",
                ))
    except Exception:
        pass

    return recommendations


def _analyze_code_generation_performance(project: Project) -> list[OptimizationRecommendation]:
    """Analyze code generation performance and provide recommendations."""
    recommendations = []

    root = Path(project.local_path).resolve() if project.local_path else None
    if not root or not root.is_dir():
        return recommendations

    # Check for redundant files
    stripe_dir = root / "stripe"
    if stripe_dir.exists():
        py_files = list(stripe_dir.glob("**/*.py"))
        if len(py_files) > 20:
            recommendations.append(OptimizationRecommendation(
                area="code_generation",
                title="Consolidate Stripe integration files",
                description=f"Large number of Stripe integration files ({len(py_files)} Python files)",
                impact="medium",
                effort="medium",
                actionable_steps=[
                    "Review for duplicate or similar functionality",
                    "Consider modularizing into logical groups",
                    "Remove unused integration files",
                ],
                estimated_improvement="Faster builds and easier maintenance",
            ))

    return recommendations


def _analyze_database_performance(project: Project) -> list[OptimizationRecommendation]:
    """Analyze database-related performance and provide recommendations."""
    recommendations = []

    from apps.deploy.postgres import get_database_url

    db_url = get_database_url(project)
    if db_url:
        # Check if using connection pooling
        if "pool" not in db_url.lower():
            recommendations.append(OptimizationRecommendation(
                area="database",
                title="Enable database connection pooling",
                description="Database connection string does not appear to use pooling",
                impact="high",
                effort="low",
                actionable_steps=[
                    "Add connection pooling parameters to DATABASE_URL",
                    "Configure pool size based on expected load",
                    "Consider using PgBouncer for high-traffic applications",
                ],
                estimated_improvement="Reduced connection overhead and better throughput",
            ))

    return recommendations


def _analyze_caching_opportunities(project: Project) -> list[OptimizationRecommendation]:
    """Identify caching opportunities."""
    recommendations = []

    root = Path(project.local_path).resolve() if project.local_path else None
    if not root or not root.is_dir():
        return recommendations

    # Check for Stripe pricing pages
    pricing_files = []
    for pattern in ["pricing", "plans", "subscription"]:
        pricing_files.extend(root.rglob(f"*{pattern}*"))

    if pricing_files:
        recommendations.append(OptimizationRecommendation(
            area="caching",
            title="Implement caching for Stripe pricing data",
            description="Pricing-related files detected - consider caching Stripe product/price data",
            impact="medium",
            effort="low",
            actionable_steps=[
                "Cache Stripe Product and Price API responses",
                "Implement cache invalidation on webhook events",
                "Use Redis or in-memory cache for frequently accessed data",
            ],
            estimated_improvement="Reduced API calls and faster page loads",
        ))

    return recommendations


def _analyze_deployment_performance(project: Project) -> list[OptimizationRecommendation]:
    """Analyze deployment-related performance."""
    recommendations = []

    scan = project.scan_data or {}
    deploy_platform = scan.get("deployPlatform")

    if deploy_platform == "vercel":
        recommendations.append(OptimizationRecommendation(
            area="deployment",
            title="Optimize Vercel deployment",
            description="Vercel deployment detected - optimization opportunities available",
            impact="medium",
            effort="low",
            actionable_steps=[
                "Enable Vercel Edge Functions for webhook endpoints",
                "Configure image optimization for static assets",
                "Use Vercel Analytics for performance monitoring",
            ],
            estimated_improvement="Faster edge response times and better UX",
        ))
    elif deploy_platform == "heroku":
        recommendations.append(OptimizationRecommendation(
            area="deployment",
            title="Optimize Heroku deployment",
            description="Heroku deployment detected - optimization opportunities available",
            impact="medium",
            effort="low",
            actionable_steps=[
                "Enable Heroku Redis for caching",
                "Configure Heroku Postgres connection pooling",
                "Use Heroku Autoscaling for variable traffic",
            ],
            estimated_improvement="Better performance under load and cost optimization",
        ))

    return recommendations


def run_performance_optimization_analysis(project: Project) -> dict[str, Any]:
    """Run comprehensive performance optimization analysis."""
    all_recommendations = []

    # Run all analyzers
    all_recommendations.extend(_analyze_webhook_performance(project))
    all_recommendations.extend(_analyze_code_generation_performance(project))
    all_recommendations.extend(_analyze_database_performance(project))
    all_recommendations.extend(_analyze_caching_opportunities(project))
    all_recommendations.extend(_analyze_deployment_performance(project))

    # Sort by impact (high first) then effort (low first)
    impact_order = {"high": 0, "medium": 1, "low": 2}
    effort_order = {"low": 0, "medium": 1, "high": 2}

    all_recommendations.sort(
        key=lambda r: (impact_order.get(r.impact, 2), effort_order.get(r.effort, 2))
    )

    # Calculate summary
    impact_counts = {"high": 0, "medium": 0, "low": 0}
    effort_counts = {"high": 0, "medium": 0, "low": 0}

    for rec in all_recommendations:
        impact_counts[rec.impact] += 1
        effort_counts[rec.effort] += 1

    return {
        "projectId": str(project.id),
        "projectSlug": project.slug,
        "recommendations": [r.to_dict() for r in all_recommendations],
        "summary": {
            "total": len(all_recommendations),
            "impactBreakdown": impact_counts,
            "effortBreakdown": effort_counts,
            "quickWins": sum(1 for r in all_recommendations if r.impact == "high" and r.effort == "low"),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
