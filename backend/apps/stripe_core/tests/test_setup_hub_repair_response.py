"""Regression test for PR #37 review: audit_secrets must not drop its repair result.

Before the fix, SetupHubActionView.post() did:

    if request.data.get("repair") and not data.get("ok"):
        data["repair"] = repair_project_secret_placement(project, hub=hub)
        data = audit_project_secret_placement(project, hub=hub).to_dict()

The second line reassigns `data` to a brand-new dict from the post-repair audit,
discarding the `data["repair"]` mutation made on the previous line. A caller
running a repair via `audit_secrets` had no way to see whether the repair
succeeded or what it did — the field silently vanished from the response.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.stripe_core.views_setup_hub import SetupHubActionView


class AuditSecretsRepairResponseTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="repair-response@example.com",
            password="test-pass-123",
        )
        self.factory = APIRequestFactory()
        # A lightweight stand-in for Project — the view only ever reads .slug
        # off it in this code path, and get_project is patched below so no
        # real ProjectOwnedMixin/DB resolution happens.
        self.project = MagicMock(slug="child-app")

    def _post_audit_secrets_with_repair(self):
        request = self.factory.post(
            "/setup-hub/child-app/actions/",
            {"action": "audit_secrets", "repair": True},
            format="json",
        )
        force_authenticate(request, user=self.user)
        view = SetupHubActionView.as_view()

        failing_report = MagicMock()
        failing_report.to_dict.return_value = {"ok": False}
        fixed_report = MagicMock()
        fixed_report.to_dict.return_value = {"ok": True}

        with patch.object(SetupHubActionView, "get_project", return_value=self.project), \
                patch("apps.stripe_core.hub_keys.get_hub_project", return_value=None), \
                patch(
                    "apps.stripe_core.views_setup_hub.audit_project_secret_placement",
                    side_effect=[failing_report, fixed_report],
                ) as mock_audit, \
                patch(
                    "apps.stripe_core.views_setup_hub.repair_project_secret_placement",
                    return_value={"ok": True, "action": "rotated_webhook_secret"},
                ) as mock_repair, \
                patch("apps.stripe_core.views_setup_hub.setup_hub_status", return_value={}):
            response = view(request, project_slug="child-app")

        return response, mock_audit, mock_repair

    def test_repair_result_survives_the_post_repair_reaudit(self):
        response, mock_audit, mock_repair = self._post_audit_secrets_with_repair()

        self.assertEqual(response.status_code, 200)
        mock_repair.assert_called_once()
        self.assertEqual(mock_audit.call_count, 2, "expected an audit before and after the repair")

        # This is the exact regression: before the fix, "repair" never survived
        # the second audit_project_secret_placement() call that overwrote `data`.
        self.assertIn("repair", response.data["audit"])
        self.assertEqual(
            response.data["audit"]["repair"],
            {"ok": True, "action": "rotated_webhook_secret"},
        )
        self.assertTrue(response.data["ok"])
