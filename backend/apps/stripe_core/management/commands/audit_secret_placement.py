"""Audit and repair Stripe/deploy secret placement across vault, Stripe, and Railway."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.projects.models import Project
from apps.stripe_core.hub_keys import HUB_SLUG, get_hub_project
from apps.stripe_core.portfolio_catalog import is_stripe_exempt_slug
from apps.stripe_core.secret_placement import (
    audit_portfolio_secret_placement,
    audit_project_secret_placement,
    repair_project_secret_placement,
)


class Command(BaseCommand):
    help = (
        "Check STRIPE_* secrets are in the right place (vault, Stripe endpoint, Railway, live route) "
        "and optionally repair by re-registering webhooks + pushing env"
    )

    def add_arguments(self, parser):
        parser.add_argument("--user", default="dallas8000@gmail.com", help="Owner email")
        parser.add_argument("--project", action="append", dest="projects", help="Project slug (repeatable)")
        parser.add_argument("--json", action="store_true", help="Print full JSON report")
        parser.add_argument(
            "--repair",
            action="store_true",
            help="Re-register webhooks + push Railway env for projects with errors",
        )
        parser.add_argument("--no-live", action="store_true", help="Skip live webhook POST probe")
        parser.add_argument("--no-railway", action="store_true", help="Skip Railway env comparison")

    def handle(self, *args, **options):
        User = get_user_model()
        email = (options.get("user") or "").strip()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"No user: {email}"))
            return

        slugs = options.get("projects") or []
        kwargs = {
            "check_live": not options.get("no_live"),
            "check_railway": not options.get("no_railway"),
        }

        if slugs:
            hub = get_hub_project(user)
            reports = []
            for slug in slugs:
                project = Project.objects.filter(owner=user, slug=slug).first()
                if not project:
                    self.stderr.write(self.style.ERROR(f"Unknown project: {slug}"))
                    continue
                report = audit_project_secret_placement(project, hub=hub, **kwargs)
                if options.get("repair") and not report.ok and not report.stripeExempt:
                    repair = repair_project_secret_placement(project, hub=hub)
                    report = audit_project_secret_placement(project, hub=hub, **kwargs)
                    report_dict = report.to_dict()
                    report_dict["repair"] = repair
                    reports.append(report_dict)
                else:
                    reports.append(report.to_dict())
            payload = {
                "ok": all(r.get("ok") for r in reports if not r.get("stripeExempt")),
                "projects": reports,
            }
        else:
            payload = audit_portfolio_secret_placement(user, **kwargs)
            if options.get("repair"):
                hub = get_hub_project(user)
                repairs = []
                for row in payload.get("projects") or []:
                    if row.get("ok") or row.get("stripeExempt"):
                        continue
                    slug = row.get("projectSlug")
                    project = Project.objects.filter(owner=user, slug=slug).first()
                    if project:
                        repairs.append(repair_project_secret_placement(project, hub=hub))
                payload["repairs"] = repairs
                payload = audit_portfolio_secret_placement(user, **kwargs)

        if options.get("json"):
            self.stdout.write(json.dumps(payload, indent=2))
            return

        self._print_summary(payload)

    def _print_summary(self, payload: dict) -> None:
        projects = payload.get("projects") or []
        if not projects:
            self.stdout.write(self.style.WARNING("No projects to audit."))
            return

        for row in projects:
            slug = row.get("projectSlug", "?")
            if row.get("stripeExempt"):
                self.stdout.write(f"\n{slug}: EXEMPT")
                continue

            status = self.style.SUCCESS("OK") if row.get("ok") else self.style.ERROR("ISSUES")
            self.stdout.write(f"\n=== {slug} [{status}] ===")
            if row.get("expectedWebhookUrl"):
                self.stdout.write(f"  Webhook URL: {row['expectedWebhookUrl']}")

            vault = (row.get("vault") or {}).get("keys") or {}
            for key, meta in vault.items():
                if key == "stripeApiVerified":
                    continue
                if isinstance(meta, dict):
                    fmt = meta.get("format", "")
                    fp = meta.get("fingerprint", "")
                    self.stdout.write(f"  Vault {key}: {fmt} ({fp})")

            stripe_ep = row.get("stripeEndpoint") or {}
            if stripe_ep:
                self.stdout.write(
                    f"  Stripe endpoint: {stripe_ep.get('matchCount', 0)} match(es)"
                    f", {stripe_ep.get('duplicateHostCount', 0)} stale on same host"
                )

            railway = row.get("railway") or {}
            for key, meta in (railway.get("keys") or {}).items():
                if isinstance(meta, dict):
                    mark = "==" if meta.get("match") else "!="
                    self.stdout.write(
                        f"  Railway {key}: vault {meta.get('vault')} {mark} railway {meta.get('railway')}"
                    )

            live = row.get("liveProbe") or {}
            if live.get("httpStatus") is not None:
                self.stdout.write(
                    f"  Live probe: HTTP {live.get('httpStatus')} ({live.get('classification')})"
                )

            for issue in row.get("issues") or []:
                sev = issue.get("severity", "info").upper()
                style = self.style.ERROR if sev == "ERROR" else self.style.WARNING
                self.stdout.write(style(f"  [{sev}] {issue.get('message')}"))
                if issue.get("fix"):
                    self.stdout.write(f"         Fix: {issue['fix']}")

        ok = payload.get("ok")
        if ok:
            self.stdout.write(self.style.SUCCESS("\nAll billing projects: secrets placed correctly."))
        else:
            err = payload.get("errorCount", "?")
            self.stdout.write(
                self.style.ERROR(
                    f"\n{err} error(s) — run with --repair to re-register webhooks and push Railway env"
                )
            )
