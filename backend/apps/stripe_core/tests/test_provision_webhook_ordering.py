"""Regression test for PR #37 review: replacing a Stripe webhook endpoint must
never leave the account with zero live endpoints.

Before the fix, _register_webhook() deleted the existing endpoint BEFORE
creating its replacement whenever secret rotation failed:

    stripe.WebhookEndpoint.delete(match.id)
    created = stripe.WebhookEndpoint.create(...)

If create() then raised (rate limit, network blip, Stripe-side error), the
account was left with no webhook endpoint at all for that URL until someone
noticed. The fix creates the replacement first and only then deletes the old
one, swallowing (and surfacing as a warning) a failure to delete rather than
letting it mask the more important fact that the replacement now exists.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.stripe_core import provision

WEBHOOK_URL = "https://app.example.com/api/v1/billing/webhook/"


class RegisterWebhookOrderingTests(SimpleTestCase):
    def _existing_endpoint_mock(self, mock_stripe):
        existing = MagicMock(id="we_old", url=WEBHOOK_URL)
        mock_stripe.WebhookEndpoint.list.return_value = MagicMock(data=[existing])
        mock_stripe.WebhookEndpoint.modify.return_value = existing
        mock_stripe.StripeError = Exception
        # Secret rotation fails — Stripe doesn't expose whsec_ for existing
        # endpoints, which is exactly the case that forces a recreate.
        mock_stripe.WebhookEndpoint._static_request.side_effect = mock_stripe.StripeError(
            "secret rotation not available"
        )
        return existing

    @patch("apps.stripe_core.provision.stripe")
    def test_replacement_is_created_before_the_old_endpoint_is_deleted(self, mock_stripe):
        self._existing_endpoint_mock(mock_stripe)
        created = MagicMock(id="we_new", url=WEBHOOK_URL, secret="whsec_new")

        call_order = []
        mock_stripe.WebhookEndpoint.create.side_effect = lambda **kw: call_order.append("create") or created
        mock_stripe.WebhookEndpoint.delete.side_effect = lambda *a, **kw: call_order.append("delete")

        result = provision._register_webhook(WEBHOOK_URL, ["checkout.session.completed"])

        self.assertEqual(call_order, ["create", "delete"])
        self.assertEqual(result["id"], "we_new")
        self.assertFalse(result["reused"])
        self.assertIsNone(result["staleEndpointId"])

    @patch("apps.stripe_core.provision.stripe")
    def test_old_endpoint_is_never_deleted_when_create_fails(self, mock_stripe):
        self._existing_endpoint_mock(mock_stripe)
        mock_stripe.WebhookEndpoint.create.side_effect = mock_stripe.StripeError("stripe is down")

        with self.assertRaises(Exception):
            provision._register_webhook(WEBHOOK_URL, ["checkout.session.completed"])

        mock_stripe.WebhookEndpoint.delete.assert_not_called()

    @patch("apps.stripe_core.provision.stripe")
    def test_stale_endpoint_id_surfaces_when_delete_of_the_old_one_fails(self, mock_stripe):
        self._existing_endpoint_mock(mock_stripe)
        created = MagicMock(id="we_new", url=WEBHOOK_URL, secret="whsec_new")
        mock_stripe.WebhookEndpoint.create.return_value = created
        mock_stripe.WebhookEndpoint.delete.side_effect = mock_stripe.StripeError("already gone")

        result = provision._register_webhook(WEBHOOK_URL, ["checkout.session.completed"])

        # The replacement is live either way; a failed cleanup of the old
        # endpoint is a warning, never something that should mask success.
        self.assertEqual(result["id"], "we_new")
        self.assertEqual(result["staleEndpointId"], "we_old")
