from django.test import Client, TestCase, override_settings


@override_settings(SAAS_STRIPE_WEBHOOK_SECRET="whsec_test_secret")
class BillingWebhookCsrfTests(TestCase):
    def test_post_reaches_handler_not_csrf_blocked(self):
        """Stripe POSTs without CSRF cookie — must not get 403 Forbidden."""
        client = Client()
        response = client.post(
            "/api/v1/billing/webhook/",
            data="{}",
            content_type="application/json",
        )
        self.assertNotEqual(response.status_code, 403)
        # Missing Stripe-Signature → invalid payload (400), not CSRF block
        self.assertEqual(response.status_code, 400)
