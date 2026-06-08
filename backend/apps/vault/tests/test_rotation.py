from django.test import SimpleTestCase, override_settings

from apps.vault.crypto import VaultConfigurationError
from apps.vault.rotation import rotate_vault_master_key

OLD = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
NEW = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"


class VaultRotationTests(SimpleTestCase):
    @override_settings(VAULT_MASTER_KEY=OLD)
    def test_rejects_same_key(self):
        with self.assertRaises(VaultConfigurationError):
            rotate_vault_master_key(OLD, dry_run=True)

    @override_settings(VAULT_MASTER_KEY=OLD)
    def test_dry_run_empty_vault(self):
        from unittest.mock import patch

        with patch("apps.vault.rotation.ProjectVault.objects.select_related") as mock_qs:
            mock_qs.return_value.all.return_value = []
            result = rotate_vault_master_key(NEW, dry_run=True)
        self.assertEqual(result.secrets, 0)
        self.assertTrue(result.dry_run)
