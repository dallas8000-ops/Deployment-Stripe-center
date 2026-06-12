from django.test import SimpleTestCase

from apps.stripe_engine.stripe_config import (
    normalize_stripe_config,
    provision_config_from_stripe_file,
    tiers_from_readme,
)


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

    def test_tiers_from_readme_markdown_table(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.joinpath("README.md").write_text(
                """
## Pricing

| Tier | Price | Highlights |
|------|-------|------------|
| Starter | $29/mo | Scans, watch, exports |
| Pro | $79/mo | AI, GitHub PR automation |
| Enterprise | Custom | SSO, SLA |
""",
                encoding="utf-8",
            )
            tiers = tiers_from_readme(root)
            self.assertEqual([tier["name"] for tier in tiers], ["Starter", "Pro"])
            self.assertEqual(tiers[0]["amount"], 2900)
            self.assertEqual(tiers[1]["amount"], 7900)
