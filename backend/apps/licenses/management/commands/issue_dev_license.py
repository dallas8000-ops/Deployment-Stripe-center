"""Issue a development license for local protection testing."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.licenses.models import License
from apps.licenses.utils import generate_license_key, normalize_domain, validate_domain_format

User = get_user_model()


class Command(BaseCommand):
    help = "Create a dev license (for testing LICENSE_ENFORCEMENT_ENABLED locally)"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Customer email")
        parser.add_argument("--domain", default="localhost", help="Registered domain (default: localhost)")
        parser.add_argument("--force", action="store_true", help="Revoke existing active license for this email/domain")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        domain = normalize_domain(options["domain"])
        if not validate_domain_format(domain):
            self.stderr.write(self.style.ERROR(f"Invalid domain: {domain}"))
            raise SystemExit(1)

        if options["force"]:
            License.objects.filter(customer_email__iexact=email, registered_domain=domain).update(
                status=License.Status.REVOKED
            )

        key = generate_license_key()
        license_obj = License.objects.create(
            key=key,
            customer_email=email,
            registered_domain=domain,
            stripe_subscription_id=f"dev_{key[:12]}",
            max_instances=1,
            status=License.Status.ACTIVE,
        )

        self.stdout.write(self.style.SUCCESS(f"Dev license issued for {email} @ {domain}"))
        self.stdout.write("")
        self.stdout.write("Add to backend/.env (deployed instance):")
        self.stdout.write(f"  STRIPE_INSTALLER_LICENSE_KEY={license_obj.key}")
        self.stdout.write(f"  STRIPE_INSTALLER_DOMAIN={domain}")
        self.stdout.write("  STRIPE_INSTALLER_VALIDATION_SERVER=http://127.0.0.1:8000")
        self.stdout.write("  LICENSE_ENFORCEMENT_ENABLED=true")
        self.stdout.write("")
        self.stdout.write(f"License ID: {license_obj.pk}")
