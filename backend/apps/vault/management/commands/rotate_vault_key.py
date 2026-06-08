from django.core.management.base import BaseCommand, CommandError

from apps.vault.crypto import VaultConfigurationError
from apps.vault.rotation import rotate_vault_master_key


class Command(BaseCommand):
    help = "Rotate VAULT_MASTER_KEY — re-encrypts all vault secrets"

    def add_arguments(self, parser):
        parser.add_argument("--new-key", required=True, help="New 64-char hex or base64 32-byte key")
        parser.add_argument("--dry-run", action="store_true", help="Count secrets without writing")

    def handle(self, *args, **options):
        try:
            result = rotate_vault_master_key(options["new_key"], dry_run=options["dry_run"])
        except VaultConfigurationError as exc:
            raise CommandError(str(exc)) from exc

        mode = "dry-run" if result.dry_run else "rotated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: {result.secrets} secret(s) across {result.projects} project vault(s)"
            )
        )
        if not result.dry_run:
            self.stdout.write(
                "Update VAULT_MASTER_KEY in .env to the new key and restart all services."
            )
