"""Rename and reset the flagship Automation Center project + local registry."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

PROJECT_SLUG = "stripe-installer"
PROJECT_NAME = "Deployment & Stripe Automation Center"


class Command(BaseCommand):
    help = "Rename the flagship project, refresh registry + stripe.config.json, optional vault reset"

    def add_arguments(self, parser):
        parser.add_argument("--user", default="", help="Owner email (default: first user)")
        parser.add_argument(
            "--clear-vault",
            action="store_true",
            help="Delete all vault secrets for this project (re-enter keys in UI after)",
        )
        parser.add_argument(
            "--register-webhook",
            action="store_true",
            help="Register Live Stripe webhook via portfolio-audit --fix (needs STRIPE_SECRET_KEY)",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = (options.get("user") or "").strip()
        if email:
            try:
                owner = User.objects.get(email=email)
            except User.DoesNotExist as exc:
                raise CommandError(f"No user with email {email}") from exc
        else:
            owner = User.objects.first()
            if not owner:
                raise CommandError("No users — register via UI first")

        from django.conf import settings

        from apps.projects.models import Project
        from apps.stripe_core.setup_hub import (
            PRODUCTION_URL,
            WEBHOOK_PATH,
            register_webhooks_for_user,
            reset_workspace,
        )

        repo_root = str(settings.REPO_ROOT)

        project, created = Project.objects.get_or_create(
            owner=owner,
            slug=PROJECT_SLUG,
            defaults={
                "name": PROJECT_NAME,
                "local_path": repo_root,
                "description": "Unified Stripe setup + API Transfer deploy",
            },
        )

        result = reset_workspace(project, clear_vault=bool(options.get("clear_vault")))

        self.stdout.write(
            self.style.SUCCESS(
                f"Project {'created' if created else 'updated'}: {project.slug} — {project.name}"
            )
        )
        self.stdout.write(self.style.SUCCESS(f"Portfolio registry: {result['registryPath']}"))
        self.stdout.write(self.style.SUCCESS(f"stripe.config.json: {result['stripeConfigPath']}"))

        if result.get("vaultSecretsCleared"):
            self.stdout.write(
                self.style.WARNING(
                    f"Cleared {result['vaultSecretsCleared']} vault secret(s) — re-add keys in the app Vault UI"
                )
            )

        if options.get("register_webhook"):
            from apps.vault.models import get_secret
            import os

            secret = os.environ.get("STRIPE_SECRET_KEY", "").strip() or get_secret(
                project, "STRIPE_SECRET_KEY"
            )
            if not secret:
                raise CommandError(
                    "STRIPE_SECRET_KEY not in env or vault — add keys in Vault UI, then re-run with --register-webhook"
                )
            results = register_webhooks_for_user(owner)
            for row in results:
                if row.get("ok"):
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Webhook: {row.get('webhookUrl')} (endpoint {row.get('endpointId', 'reused')})"
                        )
                    )
                else:
                    self.stdout.write(self.style.ERROR(f"Webhook failed: {row.get('message')}"))

        self.stdout.write("\nNext steps in the app (http://localhost:5173):")
        self.stdout.write(f"  1. Open project /projects/{PROJECT_SLUG}")
        self.stdout.write("  2. Setup Hub — add STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY (Live or Test)")
        self.stdout.write("  3. Run full setup from Setup Hub or pipeline buttons")
        self.stdout.write("  4. Stripe Dashboard -> Webhooks — confirm endpoint appears")
        self.stdout.write(f"     Expected: {PRODUCTION_URL}{WEBHOOK_PATH}")
