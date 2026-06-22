"""Ensure VAULT_MASTER_KEY is stable — local file sync + Railway pin instructions."""

from __future__ import annotations

import os
import secrets

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.vault.master_key import (
    master_key_path,
    sync_local_master_key_from_env,
    vault_master_key_status,
)


class Command(BaseCommand):
    help = (
        "Diagnose and stabilize VAULT_MASTER_KEY. Local dev auto-generates a file; "
        "Railway requires you to copy the same key into Railway Variables manually."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-local",
            action="store_true",
            help="Copy VAULT_MASTER_KEY from .env into ~/.stripe-installer/vault-master-key",
        )
        parser.add_argument(
            "--generate",
            action="store_true",
            help="Generate a new 64-char hex key (only if starting fresh — re-enter vault secrets after)",
        )
        parser.add_argument(
            "--show-key",
            action="store_true",
            help="Print the master key for copying to Railway Variables (handle securely)",
        )

    def handle(self, *args, **options):
        status = vault_master_key_status()
        path = master_key_path()

        self.stdout.write("Vault master key status\n")
        self.stdout.write(f"  Source: {status['source']}")
        self.stdout.write(f"  Stable: {status['stable']}")
        self.stdout.write(f"  Detail: {status['detail']}")
        self.stdout.write(f"  File:   {status['filePath']} ({'exists' if status['hasFileKey'] else 'missing'})")
        self.stdout.write(f"  .env:   {'set' if status['hasEnvKey'] else 'not set'}")

        if status["hasEnvKey"] and status["hasFileKey"] and not status["keysMatch"]:
            self.stdout.write(
                self.style.ERROR(
                    "\nMISMATCH: backend/.env VAULT_MASTER_KEY differs from vault-master-key file. "
                    "Run: python manage.py ensure_vault_master_key --sync-local"
                )
            )

        if options["sync_local"]:
            synced = sync_local_master_key_from_env()
            if synced:
                self.stdout.write(self.style.SUCCESS(f"\nSynced VAULT_MASTER_KEY from .env to {path}"))
            else:
                self.stdout.write(
                    self.style.WARNING("\nVAULT_MASTER_KEY not in environment — nothing to sync")
                )

        if options["generate"]:
            key = secrets.token_hex(32)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(key + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"\nGenerated new key at {path}"))
            self.stdout.write(
                self.style.WARNING(
                    "Add this line to backend/.env and Railway Variables, then re-enter all vault secrets:"
                )
            )
            if options["show_key"]:
                self.stdout.write(f"VAULT_MASTER_KEY={key}")
            else:
                self.stdout.write("Re-run with --show-key to print the value.")

        if status["onRailway"] and not status["stable"]:
            self._railway_pin_instructions(options["show_key"])
        elif not status["onRailway"]:
            self._local_railway_instructions(options["show_key"])

        if not status["stable"]:
            raise SystemExit(1)

    def _local_railway_instructions(self, show_key: bool) -> None:
        key = (settings.VAULT_MASTER_KEY or "").strip()
        if not key:
            return
        self.stdout.write("\n--- Pin the SAME key on Railway (required for production) ---")
        self.stdout.write("1. Open Railway -> stripe-installer-production -> Variables")
        self.stdout.write("2. Add or update: VAULT_MASTER_KEY")
        if show_key:
            self.stdout.write(f"   Value: {key}")
        else:
            self.stdout.write("   Value: run with --show-key to print your local key")
        self.stdout.write("3. Redeploy the service")
        self.stdout.write("4. Verify: curl https://<your-domain>/health/  (vault: ok)")
        self.stdout.write(
            self.style.WARNING(
                "\nRailway never reads backend/.env automatically — you must paste this variable in the dashboard."
            )
        )

    def _railway_pin_instructions(self, show_key: bool) -> None:
        self.stdout.write(self.style.ERROR("\nRailway is NOT using a pinned VAULT_MASTER_KEY"))
        self.stdout.write("Fix now before saving more secrets:")
        self.stdout.write("1. On your dev machine run:")
        self.stdout.write("     python manage.py ensure_vault_master_key --show-key")
        self.stdout.write("2. Railway -> Variables -> set VAULT_MASTER_KEY to that exact value")
        self.stdout.write("3. Redeploy")
        self.stdout.write(
            "4. If secrets were already lost, re-enter keys in each project Vault after redeploy"
        )
        if show_key and os.environ.get("VAULT_MASTER_KEY"):
            self.stdout.write(f"\nCurrent env key: {os.environ['VAULT_MASTER_KEY'].strip()}")
