from django.test import SimpleTestCase

from apps.api_transfer.secret_classification import is_sensitive_env_key, partition_env_vars


class SecretClassificationTests(SimpleTestCase):
    def test_sensitive_keys_detected(self):
        for key in (
            "STRIPE_SECRET_KEY",
            "DATABASE_URL",
            "API_KEY",
            "GITHUB_TOKEN",
            "AWS_ACCESS_KEY_ID",
        ):
            self.assertTrue(is_sensitive_env_key(key), key)

    def test_public_keys_not_sensitive(self):
        for key in ("PORT", "NODE_ENV", "CLIENT_URL", "ALLOWED_HOSTS"):
            self.assertFalse(is_sensitive_env_key(key), key)

    def test_partition_env_vars(self):
        env, secrets = partition_env_vars(
            {
                "PORT": "8000",
                "STRIPE_SECRET_KEY": "sk_test_x",
                "CLIENT_URL": "https://example.com",
            }
        )
        self.assertEqual(env, {"PORT": "8000", "CLIENT_URL": "https://example.com"})
        self.assertEqual(secrets, {"STRIPE_SECRET_KEY": "sk_test_x"})
