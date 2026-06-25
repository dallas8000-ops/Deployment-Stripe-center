"""Ensure one canonical URL chain for Stripe provision vs UI display."""

from django.test import TestCase

from apps.projects.models import Project
from apps.stripe_core.hub_keys import (
    resolve_expected_webhook_url,
    resolve_production_app_url,
    resolve_stripe_billing_urls,
    resolve_web_app_url,
    resolve_webhook_path,
)


class HubUrlResolutionTests(TestCase):
    def test_catalog_wins_over_stale_registry_for_agripay(self):
        project = Project(slug="agripay-logistics-ai", framework="django")
        self.assertEqual(
            resolve_production_app_url(project),
            "https://agripay-api-production.up.railway.app",
        )
        self.assertEqual(resolve_webhook_path(project), "/webhooks/stripe/")
        self.assertEqual(
            resolve_expected_webhook_url(project),
            "https://agripay-api-production.up.railway.app/webhooks/stripe/",
        )

    def test_elite_fintech_api_not_web_for_billing(self):
        project = Project(slug="elite-fintech-systems", framework="django")
        api = resolve_production_app_url(project)
        web = resolve_web_app_url(project)
        self.assertIn("elite-fintech-api", api)
        self.assertIn("elite-fintech-web", web)
        billing_api, webhook = resolve_stripe_billing_urls(project)
        self.assertEqual(billing_api, api)
        self.assertNotEqual(billing_api, web)
        self.assertIn("elite-fintech-api", webhook)

    def test_hub_webhook_is_installer_only(self):
        hub = Project(slug="stripe-installer", framework="django")
        self.assertIn("stripe-installer-production", resolve_expected_webhook_url(hub))
        self.assertIn("/api/v1/billing/webhook", resolve_expected_webhook_url(hub))
