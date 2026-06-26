"""HTTP health check for portfolio Live demo URLs (Gilliom site + hub catalog)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from apps.stripe_core.portfolio_audit import _probe_url
from apps.stripe_core.portfolio_catalog import (
    PORTFOLIO_CATALOG,
    PORTFOLIO_LIVE_URLS,
    PORTFOLIO_LIVE_URL_SLUGS,
    catalog_by_slug,
    catalog_live_urls,
)
from apps.stripe_core.portfolio_paths import portfolio_reports_dir


@dataclass
class PortfolioLinkRow:
    link_id: str
    label: str
    url: str
    project_slug: str
    status_code: int | None
    ok: bool
    latency_ms: float
    message: str
    catalog_drift: str = ""
    warnings: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "linkId": self.link_id,
            "label": self.label,
            "url": self.url,
            "projectSlug": self.project_slug,
            "statusCode": self.status_code,
            "ok": self.ok,
            "latencyMs": round(self.latency_ms, 1),
            "message": self.message,
            "catalogDrift": self.catalog_drift,
            "warnings": self.warnings,
            "issues": self.issues,
        }


def _catalog_demo_url_for_slug(slug: str) -> str:
    entry = catalog_by_slug(slug)
    if not entry:
        return ""
    live = catalog_live_urls(entry)
    return str(live.get("portfolioDemoUrl") or live.get("demoUrl") or live.get("webUrl") or "").rstrip("/")


def _link_label(link_id: str, slug: str) -> str:
    if slug:
        entry = catalog_by_slug(slug)
        if entry:
            return str(entry.get("name") or link_id)
    return link_id.replace("_", " ").title()


def run_portfolio_link_audit(*, timeout: float = 15.0) -> dict[str, Any]:
    """Probe every portfolio Live demo URL; flag HTTP failures and catalog drift."""
    rows: list[PortfolioLinkRow] = []

    for link_id, url in sorted(PORTFOLIO_LIVE_URLS.items()):
        url = url.strip()
        slug = PORTFOLIO_LIVE_URL_SLUGS.get(link_id, "")
        warnings: list[str] = []
        issues: list[str] = []
        catalog_drift = ""

        expected = _catalog_demo_url_for_slug(slug) if slug else ""
        if expected and expected.rstrip("/") != url.rstrip("/"):
            catalog_drift = f"hub catalog expects {expected} (portfolio site uses {url})"
            warnings.append(catalog_drift)

        host = (urlparse(url).hostname or "").lower()
        if host.endswith("onrender.com"):
            issues.append("legacy Render host — update portfolioLiveUrls.ts")

        probe = _probe_url(url, timeout=timeout)
        ok = probe.reachable and (probe.status_code is None or probe.status_code < 500)
        if not ok:
            issues.append(probe.message or "unreachable")

        rows.append(
            PortfolioLinkRow(
                link_id=link_id,
                label=_link_label(link_id, slug),
                url=url,
                project_slug=slug,
                status_code=probe.status_code,
                ok=ok,
                latency_ms=probe.latency_ms,
                message=probe.message,
                catalog_drift=catalog_drift,
                warnings=warnings,
                issues=issues,
            )
        )

    failing = [r for r in rows if not r.ok]
    return {
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "links": [r.to_dict() for r in rows],
        "summary": {
            "total": len(rows),
            "ok": len(rows) - len(failing),
            "failing": len(failing),
        },
    }


def save_portfolio_link_report(data: dict[str, Any]) -> Path:
    reports = portfolio_reports_dir()
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = reports / f"portfolio-link-audit-{stamp}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def catalog_entries_missing_from_live_urls() -> list[dict[str, str]]:
    """Active catalog apps not represented in PORTFOLIO_LIVE_URLS."""
    covered = set(PORTFOLIO_LIVE_URL_SLUGS.values())
    gaps: list[dict[str, str]] = []
    for entry in PORTFOLIO_CATALOG:
        if entry.get("merged"):
            continue
        slug = str(entry.get("projectSlug") or "")
        if slug and slug not in covered:
            gaps.append({"projectSlug": slug, "name": str(entry.get("name") or slug)})
    return gaps
