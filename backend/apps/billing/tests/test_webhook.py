import hashlib
import hmac
import json
import time

from django.test import Client, TestCase, override_settings


@override_settings(
    SAAS_STRIPE_WEBHOOK_SECRET="whsec_test_secret",
    SAAS_STRIPE_SECRET_KEY="sk_test_fake",
)
class BillingWebhookDeliveryTests(TestCase):
    def _sign(self, payload: str) -> dict[str, str]:
        ts = str(int(time.time()))
        sig = hmac.new(
            b"whsec_test_secret",
            f"{ts}.{payload}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "HTTP_STRIPE_SIGNATURE": f"t={ts},v1={sig}",
        }

    def test_post_not_csrf_blocked(self):
        client = Client()
        response = client.post("/api/v1/billing/webhook/", data="{}", content_type="application/json")
        self.assertNotEqual(response.status_code, 403)
        self.assertEqual(response.status_code, 400)

    def test_unhandled_event_returns_200(self):
        payload = json.dumps(
            {
                "id": "evt_test_unhandled",
                "object": "event",
                "type": "customer.updated",
                "data": {"object": {"id": "cus_x", "object": "customer"}},
            }
        )
        client = Client()
        response = client.post(
            "/api/v1/billing/webhook/",
            data=payload,
            content_type="application/json",
            **self._sign(payload),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(b"received", response.content)
