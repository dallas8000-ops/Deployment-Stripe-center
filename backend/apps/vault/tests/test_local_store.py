import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.projects.models import Project
from apps.accounts.models import User
from apps.vault.local_store import (
    list_local_secret_keys,
    load_secret_from_local,
    local_vault_path,
    sync_project_from_local_store,
)
from apps.vault.master_key import master_key_path, resolve_vault_master_key
from apps.vault.models import ProjectVault, VaultSecret, get_secret, set_secret


class MasterKeyTests(TestCase):
    def test_generates_and_persists_master_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("apps.vault.master_key.portfolio_data_dir", return_value=Path(tmp)):
                key1 = resolve_vault_master_key()
                key2 = resolve_vault_master_key()
            self.assertEqual(key1, key2)
            self.assertEqual(len(key1), 64)
            self.assertTrue(master_key_path().is_file())

    def test_migrates_env_key_to_file_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"VAULT_MASTER_KEY": "a" * 64}, clear=False):
                with patch("apps.vault.master_key.portfolio_data_dir", return_value=Path(tmp)):
                    key = resolve_vault_master_key()
                    self.assertEqual(key, "a" * 64)
                    self.assertEqual((Path(tmp) / "vault-master-key").read_text().strip(), "a" * 64)

    def test_env_wins_over_file_on_railway(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "vault-master-key").write_text("f" * 64, encoding="utf-8")
            with patch.dict(
                "os.environ",
                {"VAULT_MASTER_KEY": "e" * 64, "RAILWAY_ENVIRONMENT": "production"},
                clear=False,
            ):
                with patch("apps.vault.master_key.portfolio_data_dir", return_value=Path(tmp)):
                    key = resolve_vault_master_key()
            self.assertEqual(key, "e" * 64)

    def test_railway_without_env_does_not_persist_generated_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"RAILWAY_ENVIRONMENT": "production"}, clear=False):
                with patch("apps.vault.master_key.portfolio_data_dir", return_value=Path(tmp)):
                    key = resolve_vault_master_key()
            self.assertEqual(len(key), 64)
            self.assertFalse((Path(tmp) / "vault-master-key").exists())


@override_settings(VAULT_MASTER_KEY="b" * 64)
class LocalStoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="v@t.com", password="pass12345")
        self.project = Project.objects.create(
            name="Local Store",
            slug="local-store",
            owner=self.user,
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self.patch_dir = patch("apps.vault.local_store.portfolio_data_dir", return_value=self.data_dir)
        self.patch_dir.start()
        self.patch_verification = patch("apps.vault.models._apply_verification")
        self.patch_verification.start()

    def tearDown(self):
        self.patch_verification.stop()
        self.patch_dir.stop()
        self.tmp.cleanup()

    def test_set_secret_writes_local_backup(self):
        set_secret(self.project, "STRIPE_SECRET_KEY", "sk_test_localstore")
        self.assertIn("STRIPE_SECRET_KEY", list_local_secret_keys(self.project.slug))
        self.assertTrue(local_vault_path(self.project.slug).is_file())

    def test_get_secret_restores_from_local_when_db_unreadable(self):
        set_secret(self.project, "STRIPE_SECRET_KEY", "sk_test_restore")
        VaultSecret.objects.filter(project=self.project).update(encrypted_value="bad")

        value = get_secret(self.project, "STRIPE_SECRET_KEY")
        self.assertEqual(value, "sk_test_restore")

    def test_sync_project_from_local_store(self):
        set_secret(self.project, "STRIPE_PUBLISHABLE_KEY", "pk_test_sync")
        ProjectVault.objects.filter(project=self.project).delete()
        VaultSecret.objects.filter(project=self.project).delete()

        imported = sync_project_from_local_store(self.project)
        self.assertIn("STRIPE_PUBLISHABLE_KEY", imported)
        self.assertEqual(get_secret(self.project, "STRIPE_PUBLISHABLE_KEY"), "pk_test_sync")
        self.assertEqual(load_secret_from_local(self.project, "STRIPE_PUBLISHABLE_KEY"), "pk_test_sync")
