from unittest.mock import MagicMock, patch

from cryptography.exceptions import InvalidTag
from django.test import SimpleTestCase

from apps.vault.models import get_secret, is_secret_readable, vault_health


class VaultDecryptTests(SimpleTestCase):
    def setUp(self):
        self.project = MagicMock(slug="decrypt-test")
        self.vault = MagicMock(salt=b"x" * 32)
        self.project.vault = self.vault
        self.secret = MagicMock(
            key_name="STRIPE_SECRET_KEY",
            encrypted_value="abc",
            iv="abc",
            auth_tag="abc",
            project=self.project,
        )

    @patch("apps.vault.models.VaultSecret.objects.get")
    @patch("apps.vault.models.decrypt_secret", side_effect=InvalidTag)
    def test_get_secret_returns_none_on_invalid_tag(self, _mock_decrypt, mock_get):
        mock_get.return_value = self.secret
        self.assertIsNone(get_secret(self.project, "STRIPE_SECRET_KEY"))

    @patch("apps.vault.models.decrypt_secret", side_effect=InvalidTag)
    def test_is_secret_readable_false_on_invalid_tag(self, _mock_decrypt):
        self.assertFalse(is_secret_readable(self.project, self.secret))

    @patch("apps.vault.models.VaultSecret.objects.filter")
    @patch("apps.vault.models.is_secret_readable", return_value=False)
    def test_vault_health_reports_unreadable(self, _mock_readable, mock_filter):
        mock_filter.return_value = [self.secret]
        health = vault_health(self.project)
        self.assertFalse(health["masterKeyValid"])
        self.assertEqual(health["unreadableCount"], 1)
