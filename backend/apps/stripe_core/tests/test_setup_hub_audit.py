"""Setup hub audit storage — portfolio gaps belong on hub, not child projects."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.projects.models import Project
from apps.stripe_core.hub_keys import HUB_SLUG
from apps.stripe_core.setup_hub import _persist_portfolio_audit, setup_hub_status


class SetupHubAuditStorageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="audit@example.com",
            password="test-pass-123",
        )
        self.hub = Project.objects.create(
            owner=self.user,
            slug=HUB_SLUG,
            name="Hub",
            local_path="C:\\hub",
        )
        self.child = Project.objects.create(
            owner=self.user,
            slug="agripay-logistics-ai",
            name="AgriPay",
            local_path="C:\\agripay",
        )

    def test_persist_portfolio_audit_splits_gaps_by_project(self):
        data = {
            "scannedAt": "2026-01-01T00:00:00Z",
            "summary": {"endpointCount": 0},
            "registryGaps": [
                {
                    "app": "automation-center",
                    "issue": "missing",
                    "expectedUrl": "https://hub.example/webhook/",
                },
                {
                    "app": "agripay-logistics",
                    "issue": "missing",
                    "expectedUrl": "https://agripay.example/webhooks/stripe/",
                },
            ],
        }
        _persist_portfolio_audit(self.child, data)

        self.hub.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(len(self.hub.scan_data["lastPortfolioAuditRegistryGaps"]), 2)
        self.assertEqual(len(self.child.scan_data["lastPortfolioAuditRegistryGaps"]), 1)
        self.assertEqual(
            self.child.scan_data["lastPortfolioAuditRegistryGaps"][0]["app"],
            "agripay-logistics",
        )

    def test_child_status_reads_audit_from_hub_not_stale_local_gaps(self):
        self.child.scan_data = {
            "lastPortfolioAuditSummary": {"endpointCount": 0},
            "lastPortfolioAuditRegistryGaps": [
                {"app": "automation-center", "issue": "stale"},
            ],
        }
        self.child.save(update_fields=["scan_data"])
        self.hub.scan_data = {
            "lastPortfolioAuditSummary": {"endpointCount": 1},
            "lastPortfolioAuditRegistryGaps": [
                {"app": "automation-center", "issue": "missing"},
            ],
        }
        self.hub.save(update_fields=["scan_data"])

        status = setup_hub_status(self.child, user=self.user)
        self.assertEqual(len(status["lastPortfolioAuditRegistryGaps"]), 0)
        self.assertEqual(len(status["projectPortfolioGaps"]), 0)
