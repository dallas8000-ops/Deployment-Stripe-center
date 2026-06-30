from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase


@override_settings(
    SAAS_STRIPE_SECRET_KEY="rk_test_billing",
    SAAS_STRIPE_PRICE_STARTER="price_starter",
    SAAS_STRIPE_PRICE_PRO="price_pro",
    SAAS_STRIPE_PRICE_ENTERPRISE="price_enterprise",
    SAAS_BILLING_RETURN_URL="https://app.example.com",
)
class CheckoutTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="checkout@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(self.user)

    @patch("apps.billing.views.stripe.checkout.Session.create")
    def test_rejects_unconfigured_price(self, create_session):
        response = self.client.post(
            "/api/v1/billing/checkout/",
            {"priceId": "price_not_ours", "domain": "app.example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Unknown or unavailable plan")
        create_session.assert_not_called()

    @patch("apps.billing.views.stripe.checkout.Session.create")
    def test_rejects_non_string_checkout_fields(self, create_session):
        response = self.client.post(
            "/api/v1/billing/checkout/",
            {"priceId": ["price_pro"], "domain": {"host": "app.example.com"}},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        create_session.assert_not_called()

    @patch("apps.billing.views.stripe.checkout.Session.create")
    def test_configured_price_creates_dynamic_payment_checkout(self, create_session):
        create_session.return_value = SimpleNamespace(url="https://checkout.stripe.com/test")

        response = self.client.post(
            "/api/v1/billing/checkout/",
            {"priceId": "price_pro", "domain": "app.example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        params = create_session.call_args.kwargs
        self.assertEqual(params["mode"], "subscription")
        self.assertEqual(params["line_items"], [{"price": "price_pro", "quantity": 1}])
        self.assertNotIn("payment_method_types", params)
