"""End-to-end smoke test for vault + pipeline API (no real Stripe keys required)."""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.projects.models import Project
from apps.vault.models import get_or_create_vault, list_vault_entries, set_secret, delete_secret


class Command(BaseCommand):
    help = "Smoke-test vault encrypt/mask/verify flow and project CRUD"

    def handle(self, *args, **options):
        User = get_user_model()
        email = "smoke@test.local"
        user, _ = User.objects.get_or_create(
            email=email,
            defaults={"display_name": "Smoke Test"},
        )
        if not user.has_usable_password():
            user.set_password("smoke-test-pass")
            user.save()

        project, _ = Project.objects.get_or_create(
            owner=user,
            slug="smoke-test",
            defaults={
                "name": "Smoke Test Project",
                "local_path": str(__import__("pathlib").Path(__file__).resolve().parents[5]),
            },
        )

        vault = get_or_create_vault(project)
        self.stdout.write(self.style.SUCCESS(f"Vault initialized: {vault.pk}"))

        secret = set_secret(project, "STRIPE_SECRET_KEY", "sk_test_smoke_not_real_key_12345")
        entry = secret.to_entry_dict()
        assert entry["display"].startswith("sk_test_"), entry["display"]
        assert "•" in entry["display"], entry["display"]
        self.stdout.write(f"  Masked display: {entry['display']}")
        self.stdout.write(f"  Verified: {entry['verified']} ({entry.get('verificationMessage')})")

        entries = list_vault_entries(project)
        assert any(e["key"] == "STRIPE_SECRET_KEY" for e in entries)
        self.stdout.write(self.style.SUCCESS(f"Vault entries: {len(entries)}"))

        delete_secret(project, "STRIPE_SECRET_KEY")
        assert "STRIPE_SECRET_KEY" not in [e["key"] for e in list_vault_entries(project)]
        self.stdout.write(self.style.SUCCESS("Delete confirmed — all smoke checks passed"))
