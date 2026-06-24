from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from apps.projects.models import Project
from apps.diagnostics.webhook_events import sanitize_stripe_value

User = get_user_model()


class SanitizeStripeValueTests(SimpleTestCase):
    def test_redacts_sensitive_keys(self):
        raw = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_secret": "sec_test",
                    "amount_total": 900,
                }
            },
        }
        cleaned = sanitize_stripe_value(raw)
        self.assertEqual(cleaned["id"], "evt_123")
        self.assertEqual(cleaned["data"]["object"]["client_secret"], "[redacted]")
        self.assertEqual(cleaned["data"]["object"]["amount_total"], 900)


class FetchStripeEventTests(SimpleTestCase):
    @patch("apps.diagnostics.webhook_events.get_secret", return_value="sk_test_x")
    @patch("apps.diagnostics.webhook_events.stripe.Event.retrieve")
    def test_fetch_stripe_event(self, mock_retrieve, _mock_secret):
        from apps.diagnostics.webhook_events import fetch_stripe_event

        mock_retrieve.return_value = MagicMock(
            to_dict=lambda: {
                "id": "evt_abc",
                "type": "invoice.paid",
                "livemode": False,
                "created": 1,
                "api_version": "2024-06-20",
                "data": {"object": {"id": "in_1"}},
                "request": None,
            }
        )
        user = User(email="t@example.com")
        project = Project(name="Demo", slug="demo", owner=user)

        result = fetch_stripe_event(project, "evt_abc")
        self.assertEqual(result["id"], "evt_abc")
        self.assertEqual(result["type"], "invoice.paid")

    def test_rejects_invalid_event_id(self):
        from apps.diagnostics.webhook_events import fetch_stripe_event

        with self.assertRaises(ValueError):
            fetch_stripe_event(Project(), "not-an-event")
