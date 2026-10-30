from django.test import TestCase, override_settings

from apps.vault.crypto import VaultConfigurationError
from apps.vault.rotation import rotate_vault_master_key

OLD = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
NEW = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"


class VaultRotationTests(TestCase):
    # rotate_vault_master_key runs inside transaction.atomic(), so it needs a real test DB.
    @override_settings(VAULT_MASTER_KEY=OLD)
    def test_rejects_same_key(self):
        with self.assertRaises(VaultConfigurationError):
            rotate_vault_master_key(OLD, dry_run=True)

    @override_settings(VAULT_MASTER_KEY=OLD)
    def test_dry_run_empty_vault(self):
        result = rotate_vault_master_key(NEW, dry_run=True)
        self.assertEqual(result.projects, 0)
        self.assertEqual(result.secrets, 0)
        self.assertTrue(result.dry_run)
