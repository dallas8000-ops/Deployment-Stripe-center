"""Reconfirm portfolio Live demo links and Railway hearty-enjoyment layout."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.railway_home_audit import RAILWAY_HOME_PROJECT_NAME, audit_railway_home_layout
from apps.projects.models import Project
from apps.stripe_core.portfolio_catalog import HUB_SLUG
from apps.stripe_core.portfolio_link_audit import (
    catalog_entries_missing_from_live_urls,
    run_portfolio_link_audit,
    save_portfolio_link_report,
)
from apps.vault.models import get_secret


class Command(BaseCommand):
    help = (
        "Probe every Gilliom portfolio Live demo URL and report Railway placement "
        f"inside {RAILWAY_HOME_PROJECT_NAME}. Does not change links unless --save-report."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print full JSON report to stdout",
        )
        parser.add_argument(
            "--save-report",
            action="store_true",
            help="Write JSON report under portfolio-reports/",
        )
        parser.add_argument(
            "--links-only",
            action="store_true",
            help="Skip Railway project layout audit",
        )
        parser.add_argument(
            "--railway-only",
            action="store_true",
            help="Skip HTTP link probes",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=15.0,
            help="HTTP probe timeout seconds",
        )

    def handle(self, *args, **options):
        report: dict = {"scannedAt": None}

        if not options["railway_only"]:
            link_data = run_portfolio_link_audit(timeout=options["timeout"])
            report["links"] = link_data
            report["scannedAt"] = link_data.get("scannedAt")
            gaps = catalog_entries_missing_from_live_urls()
            if gaps:
                report["catalogGaps"] = gaps

            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Portfolio Live demo links ===\n"))
            for row in link_data.get("links") or []:
                status = row.get("statusCode")
                code = str(status) if status is not None else "—"
                style = self.style.SUCCESS if row.get("ok") else self.style.ERROR
                self.stdout.write(
                    style(f"  [{code}] {row.get('label')} — {row.get('url')}")
                )
                for issue in row.get("issues") or []:
                    self.stdout.write(self.style.ERROR(f"         ! {issue}"))
                for warn in row.get("warnings") or []:
                    self.stdout.write(self.style.WARNING(f"         ~ {warn}"))

            summary = link_data.get("summary") or {}
            self.stdout.write(
                f"\nLinks: {summary.get('ok', 0)}/{summary.get('total', 0)} OK"
            )

        if not options["links_only"]:
            token = self._railway_token()
            railway_data = audit_railway_home_layout(token)
            report["railway"] = railway_data

            self.stdout.write(
                self.style.MIGRATE_HEADING(f"\n=== Railway layout ({RAILWAY_HOME_PROJECT_NAME}) ===\n")
            )
            home = railway_data.get("homeProject") or {}
            self.stdout.write(
                f"Home project: {home.get('name')} — {home.get('serviceCount', 0)} services"
            )

            outside = railway_data.get("outsideHeartyEnjoyment") or []
            if outside:
                self.stdout.write(self.style.WARNING("\nApps NOT in hearty-enjoyment:"))
                for row in outside:
                    self.stdout.write(
                        f"  {row.get('name')} → {row.get('railwayProject')} "
                        f"({row.get('railwayService')})"
                    )
                self.stdout.write(
                    self.style.WARNING(
                        "\nTo move AgriPay into hearty-enjoyment:\n"
                        "  python manage.py consolidate_railway_monorepo --dry-run\n"
                        "  python manage.py consolidate_railway_monorepo --confirm"
                    )
                )
            else:
                self.stdout.write(self.style.SUCCESS("\nAll portfolio apps resolve inside hearty-enjoyment."))

            extra = railway_data.get("extraRailwayProjects") or []
            if extra:
                self.stdout.write(self.style.WARNING("\nOther Railway projects (candidates to delete after migrate):"))
                for proj in extra:
                    self.stdout.write(
                        f"  {proj.get('name')} — {proj.get('serviceCount')} services"
                    )

        if options["save_report"]:
            path = save_portfolio_link_report(report)
            self.stdout.write(self.style.SUCCESS(f"\nReport saved: {path}"))

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2))

        link_summary = (report.get("links") or {}).get("summary") or {}
        if link_summary.get("failing"):
            raise CommandError(
                f"{link_summary['failing']} portfolio link(s) failed — fix URLs or Railway services"
            )

    def _railway_token(self) -> str:
        try:
            hub = Project.objects.get(slug=HUB_SLUG)
        except Project.DoesNotExist as exc:
            raise CommandError("Hub project stripe-installer not found") from exc
        token = (get_secret(hub, "RAILWAY_API_TOKEN") or "").strip()
        if not token:
            raise CommandError("RAILWAY_API_TOKEN missing from hub vault")
        return token
