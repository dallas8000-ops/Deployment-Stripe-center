"""Validate license on startup (Docker entrypoint / production)."""

from django.core.management.base import BaseCommand

from apps.licenses.service import license_enforcement_enabled, license_status


class Command(BaseCommand):
    help = "Validate STRIPE_INSTALLER license from environment (exit 1 if invalid)"

    def handle(self, *args, **options):
        status = license_status()
        if status["enforcement"] == "disabled":
            self.stdout.write(self.style.WARNING(status["message"]))
            return

        if status["valid"]:
            self.stdout.write(self.style.SUCCESS(f"License valid for {status.get('domain')}"))
            return

        self.stderr.write(self.style.ERROR(status.get("message", "License invalid")))
        raise SystemExit(1)
