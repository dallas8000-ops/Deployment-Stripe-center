import base64
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.test import TestCase

from apps.accounts.models import User
from apps.projects.models import Project
from apps.vault.legacy_vault import decrypt_legacy_vault, list_legacy_vault_keys
from apps.vault.secret_sources import discover_secret_sources, import_from_env_path, is_importable_key


class ImportableKeyTests(TestCase):
    def test_stripe_prefixed_keys(self):
        self.assertTrue(is_importable_key("SAAS_STRIPE_WEBHOOK_SECRET"))
        self.assertTrue(is_importable_key("SPECWRIGHT_STRIPE_SECRET_KEY"))
        self.assertFalse(is_importable_key("RANDOM_VAR"))


class LegacyVaultTests(TestCase):
    def test_decrypt_legacy_roundtrip(self):
        passphrase = "test-passphrase"
        salt = b"s" * 32
        plaintext = "sk_test_legacy"

        key = hashlib.scrypt(passphrase.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        iv = b"i" * 12
        aesgcm = AESGCM(key)
        ciphertext_with_tag = aesgcm.encrypt(iv, plaintext.encode(), None)
        auth_tag = ciphertext_with_tag[-16:]
        ciphertext = ciphertext_with_tag[:-16]

        entry = {
            "STRIPE_SECRET_KEY": {
                "key": "STRIPE_SECRET_KEY",
                "encryptedValue": base64.b64encode(ciphertext).decode(),
                "iv": base64.b64encode(iv).decode(),
                "authTag": base64.b64encode(auth_tag).decode(),
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy_dir = root / ".stripe-installer"
            legacy_dir.mkdir()
            (legacy_dir / "vault.salt").write_bytes(salt)
            (legacy_dir / "vault.enc.json").write_text(json.dumps(entry), encoding="utf-8")

            self.assertEqual(list_legacy_vault_keys(root), ["STRIPE_SECRET_KEY"])
            secrets = decrypt_legacy_vault(root, passphrase)
            self.assertEqual(secrets["STRIPE_SECRET_KEY"], plaintext)


class DiscoverSourcesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="discover@test.com", password="pass12345")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".env.local").write_text("STRIPE_SECRET_KEY=sk_test_env\n", encoding="utf-8")
        self.project = Project.objects.create(
            name="Discover",
            slug="discover-test",
            owner=self.user,
            local_path=str(self.root),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_discover_finds_env_file(self):
        with patch("apps.vault.local_store.portfolio_data_dir", return_value=Path(self.tmp.name)):
            data = discover_secret_sources(self.project)
        env_sources = [s for s in data["sources"] if s["kind"] == "env_file"]
        self.assertTrue(any(s["keyCount"] >= 1 for s in env_sources))

    def test_import_from_env_path(self):
        with patch("apps.vault.local_store.portfolio_data_dir", return_value=Path(self.tmp.name)):
            keys = import_from_env_path(self.project, self.root / ".env.local")
        self.assertIn("STRIPE_SECRET_KEY", keys)
