from django.test import SimpleTestCase, override_settings

from apps.api_transfer.sealed_secrets import SealedSecret, decrypt_secret, encrypt_secret

_VAULT_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


@override_settings(VAULT_MASTER_KEY=_VAULT_KEY)
class SealedSecretsTests(SimpleTestCase):
    def test_round_trip(self):
        sealed = encrypt_secret("platform-transfer-secret")
        self.assertIsInstance(sealed, SealedSecret)
        self.assertEqual(decrypt_secret(sealed), "platform-transfer-secret")

    def test_from_dict_round_trip(self):
        sealed = encrypt_secret("another-secret")
        restored = SealedSecret.from_dict(sealed.to_dict())
        self.assertEqual(decrypt_secret(restored), "another-secret")
