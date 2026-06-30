import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.test import SimpleTestCase

from apps.stripe_core.portfolio_audit import _probe_url
from apps.stripe_core.portfolio_catalog import catalog_by_slug
from apps.stripe_core.provision import _register_webhook
from apps.stripe_core.provision import load_manifest, save_manifest
from apps.stripe_core.repair import _normalize_webhook_url


class WebhookRedirectTests(SimpleTestCase):
    def test_specwright_catalog_uses_direct_fastapi_routes(self):
        entry = catalog_by_slug("specwright")

        self.assertIsNotNone(entry)
        self.assertEqual(entry["webhookPath"], "/api/v1/billing/webhook")
        self.assertEqual(entry["healthPath"], "/api/v1/health")

    @patch("apps.stripe_core.portfolio_audit.urllib.request.build_opener")
    def test_probe_reports_redirect_as_unreachable(self, build_opener):
        opener = MagicMock()
        opener.open.side_effect = HTTPError(
            "https://example.com/webhook/",
            307,
            "Temporary Redirect",
            {"Location": "https://example.com/webhook"},
            None,
        )
        build_opener.return_value = opener

        result = _probe_url("https://example.com/webhook/")

        self.assertFalse(result.reachable)
        self.assertEqual(result.status_code, 307)
        self.assertEqual(result.redirect_url, "https://example.com/webhook")

    @patch("apps.stripe_core.provision.stripe.WebhookEndpoint.delete")
    @patch("apps.stripe_core.provision.stripe.WebhookEndpoint.modify")
    @patch("apps.stripe_core.provision.stripe.WebhookEndpoint.list")
    def test_registration_normalizes_existing_slash_variant(
        self, list_endpoints, modify_endpoint, _delete_endpoint
    ):
        existing = SimpleNamespace(id="we_test", url="https://example.com/webhook/")
        list_endpoints.return_value = SimpleNamespace(data=[existing])
        modify_endpoint.return_value = SimpleNamespace(
            id="we_test", url="https://example.com/webhook"
        )

        result = _register_webhook(
            "https://example.com/webhook",
            ["checkout.session.completed"],
        )

        self.assertTrue(result["reused"])
        self.assertTrue(result["urlCorrected"])
        modify_endpoint.assert_called_once_with(
            "we_test",
            url="https://example.com/webhook",
            enabled_events=["checkout.session.completed"],
            disabled=False,
        )

    @patch("apps.stripe_core.repair.get_secret", return_value="sk_test_safe")
    @patch(
        "apps.stripe_core.repair.resolve_stripe_billing_urls",
        return_value=("https://example.com", "https://example.com/webhook"),
    )
    @patch("stripe.WebhookEndpoint.modify")
    @patch("stripe.WebhookEndpoint.retrieve")
    def test_safe_heal_normalizes_only_trailing_slash(
        self, retrieve_endpoint, modify_endpoint, _resolve_urls, _get_secret
    ):
        retrieve_endpoint.return_value = SimpleNamespace(
            id="we_test", url="https://example.com/webhook/"
        )
        project = SimpleNamespace(slug="specwright")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_manifest(
                root,
                {"webhookEndpoint": {"id": "we_test", "url": "https://example.com/webhook/"}},
            )

            result = _normalize_webhook_url(project, root)
            updated = load_manifest(root)

        self.assertTrue(result.success)
        self.assertEqual(updated["webhookEndpoint"]["url"], "https://example.com/webhook")
        modify_endpoint.assert_called_once_with(
            "we_test", url="https://example.com/webhook"
        )
