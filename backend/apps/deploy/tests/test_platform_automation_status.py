from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.deploy.platform_bootstrap import platform_automation_status


class PlatformAutomationStatusTests(SimpleTestCase):
    @patch("apps.deploy.railway_resolve.ensure_railway_targets_detected")
    @patch("apps.deploy.platform_bootstrap._host_railway_ids", return_value=("", "", ""))
    @patch("apps.deploy.platform_bootstrap._hub_railway_token", return_value="token")
    @patch(
        "apps.deploy.platform_bootstrap.vault_health",
        return_value={"unreadableCount": 0},
    )
    @patch(
        "apps.deploy.platform_bootstrap.vault_master_key_status",
        return_value={
            "stable": True,
            "source": "environment",
            "detail": "ready",
            "keysMatch": True,
            "onRailway": False,
        },
    )
    def test_provider_failure_is_reported_without_breaking_status(
        self,
        _key_status,
        _vault_health,
        _token,
        _ids,
        detect,
    ):
        detect.side_effect = OSError("network unavailable")
        project = SimpleNamespace(scan_data={"deployPlatform": "railway"}, local_path="")

        status = platform_automation_status(project)

        self.assertFalse(status["railway"]["detected"])
        self.assertIn("discovery unavailable", status["railway"]["detectionMessage"])
