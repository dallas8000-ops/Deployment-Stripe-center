"""Re-attach gilliomfrontlinedigital.com to FrontLineDigital-1 on Railway."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.deploy.env_push import _railway_environment_id, _railway_gql
from apps.projects.models import Project
from apps.vault.models import get_secret

HOME_PROJECT_ID = "e5dce2f2-ffc6-4677-8f16-d3912934cebd"
FRONTLINE_SERVICE_ID = "6592cd9b-10b8-4b0b-9d7f-9d56d4e64365"
PORTFOLIO_DOMAIN = "gilliomfrontlinedigital.com"


class Command(BaseCommand):
    help = "Attach portfolio custom domain to FrontLineDigital-1 and print Porkbun DNS records."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="stripe-installer")
        parser.add_argument("--domain", default=PORTFOLIO_DOMAIN)
        parser.add_argument("--create", action="store_true", help="Create domain if missing")

    def handle(self, *args, **options):
        slug = options["slug"].strip().lower()
        domain = options["domain"].strip().lower()
        try:
            project = Project.objects.get(slug=slug)
        except Project.DoesNotExist:
            project = Project.objects.filter(slug__icontains="stripe").first()
        if not project:
            raise CommandError("Hub project not found for Railway token")

        token = (get_secret(project, "RAILWAY_API_TOKEN") or "").strip()
        if not token:
            raise CommandError("RAILWAY_API_TOKEN missing from vault")

        env_id = _railway_environment_id(token, HOME_PROJECT_ID)
        existing = self._list_custom_domains(token, FRONTLINE_SERVICE_ID, env_id)
        match = next((d for d in existing if (d.get("domain") or "").lower() == domain), None)

        if match:
            self.stdout.write(self.style.SUCCESS(f"Custom domain already on FrontLineDigital-1: {domain}"))
            self._print_dns(match)
            return

        if not options["create"]:
            self.stdout.write(
                self.style.WARNING(
                    f"No custom domain '{domain}' on FrontLineDigital-1. "
                    "Pass --create to register it on Railway."
                )
            )
            return

        created = _railway_gql(
            token,
            """
            mutation($input: CustomDomainCreateInput!) {
              customDomainCreate(input: $input) {
                id
                domain
                status {
                  verified
                  certificateStatus
                  verificationToken
                  verificationDnsHost
                  dnsRecords { hostlabel fqdn recordType requiredValue status }
                }
              }
            }
            """,
            {
                "input": {
                    "domain": domain,
                    "environmentId": env_id,
                    "projectId": HOME_PROJECT_ID,
                    "serviceId": FRONTLINE_SERVICE_ID,
                }
            },
        )
        row = created.get("customDomainCreate") or {}
        self.stdout.write(self.style.SUCCESS(f"Created custom domain: {row.get('domain')}"))
        self._print_dns(row)

    def _list_custom_domains(self, token: str, service_id: str, env_id: str) -> list[dict]:
        data = _railway_gql(
            token,
            """
            query($sid: String!) {
              service(id: $sid) {
                serviceInstances {
                  edges { node {
                    domains { customDomains { id domain status {
                      verified certificateStatus verificationToken verificationDnsHost
                      dnsRecords { hostlabel fqdn recordType requiredValue status }
                    } } }
                  } }
                }
              }
            }
            """,
            {"sid": service_id},
        )
        rows: list[dict] = []
        edges = (
            ((data.get("service") or {}).get("serviceInstances") or {}).get("edges") or []
        )
        for edge in edges:
            domains = ((edge.get("node") or {}).get("domains") or {}).get("customDomains") or []
            rows.extend(domains)
        return rows

    def _print_dns(self, row: dict) -> None:
        status = row.get("status") or {}
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Porkbun DNS (required)"))
        self.stdout.write(
            "Remove the root A record (69.46.46.126). Railway needs ALIAS/CNAME + TXT, not a bare A record."
        )
        for rec in status.get("dnsRecords") or []:
            self.stdout.write(
                f"  {rec.get('recordType')} {rec.get('hostlabel') or '@'} -> {rec.get('requiredValue')} "
                f"({rec.get('status')})"
            )
        token = status.get("verificationToken")
        host = status.get("verificationDnsHost") or "_railway-verify"
        if token:
            self.stdout.write(f"  TXT {host} -> {token}")
        self.stdout.write("")
        self.stdout.write(f"verified={status.get('verified')} cert={status.get('certificateStatus')}")
        self.stdout.write(
            "Dashboard: https://railway.app/project/"
            f"{HOME_PROJECT_ID}/service/{FRONTLINE_SERVICE_ID}/settings"
        )
