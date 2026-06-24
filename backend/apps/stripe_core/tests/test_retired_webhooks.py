from django.test import SimpleTestCase

from apps.stripe_core.portfolio_catalog import retired_webhook_hosts, retired_webhook_urls


class RetiredWebhookTests(SimpleTestCase):
    def test_api_transfer_legacy_url(self):
        urls = retired_webhook_urls()
        self.assertIn(
            "https://api-transfer-production.up.railway.app/api/billing/webhook",
            urls,
        )
        self.assertIn("api-transfer-production.up.railway.app", retired_webhook_hosts())
