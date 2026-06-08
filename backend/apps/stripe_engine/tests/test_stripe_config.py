from django.test import SimpleTestCase

from apps.stripe_engine.stripe_config import normalize_stripe_config, provision_config_from_stripe_file


class StripeConfigTests(SimpleTestCase):
    def test_normalize_requires_tier_fields(self):
        with self.assertRaises(ValueError):
            normalize_stripe_config({"tiers": [{"name": "OnlyName"}]})

    def test_provision_config_builds_webhook_url(self):
        import tempfile
        from pathlib import Path

        from apps.stripe_engine.stripe_config import write_stripe_config

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_stripe_config(
                root,
                {
                    "appUrl": "https://app.example.com",
                    "tiers": [{"name": "Starter", "amount": 900, "interval": "month"}],
                },
            )
            opts = provision_config_from_stripe_file(
                root,
                app_url="https://app.example.com",
                webhook_path="/api/stripe/webhook",
            )
            self.assertEqual(opts["webhook_url"], "https://app.example.com/api/stripe/webhook")
            self.assertEqual(opts["tiers"][0]["name"], "Starter")
