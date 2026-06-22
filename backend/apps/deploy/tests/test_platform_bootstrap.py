from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
import tempfile
from pathlib import Path

from apps.deploy.platform_bootstrap import (
    automate_project_deploy,
    platform_automation_status,
    reconcile_local_master_key,
    sync_deploy_platform_from_disk,
)
from apps.projects.models import Project


class PlatformBootstrapTests(SimpleTestCase):
    @override_settings(VAULT_MASTER_KEY="a" * 64)
    def test_reconcile_local_ok_when_file_present(self):
        with patch("apps.deploy.platform_bootstrap.vault_master_key_status") as mock_status:
            mock_status.return_value = {
                "onRailway": False,
                "stable": True,
                "detail": "ok",
                "hasEnvKey": True,
                "hasFileKey": True,
                "keysMatch": True,
            }
            result = reconcile_local_master_key()
        self.assertEqual(result["action"], "ok")

    def test_sync_deploy_platform_from_disk(self):
        User = get_user_model()
        user = User(email="bootstrap@test.local")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "deploy.config.json").write_text(
                '{"platform": "railway", "productionUrl": "https://app.example.com"}',
                encoding="utf-8",
            )
            project = Project(
                owner=user,
                name="Test",
                slug="bootstrap-sync",
                local_path=str(root),
                scan_data={},
            )
            with patch("apps.deploy.config.sync_project_from_config") as mock_sync:
                platform = sync_deploy_platform_from_disk(project)
            self.assertEqual(platform, "railway")
            mock_sync.assert_called_once()

    @override_settings(VAULT_MASTER_KEY="b" * 64, RAILWAY_API_TOKEN="")
    def test_platform_automation_status(self):
        User = get_user_model()
        user = User(email="bootstrap@test.local")
        project = Project(owner=user, name="Hub", slug="stripe-installer", scan_data={})
        with patch("apps.deploy.platform_bootstrap.get_secret", return_value=None):
            with patch("apps.deploy.platform_bootstrap.vault_health", return_value={"unreadableCount": 0, "totalCount": 2}):
                with patch("apps.deploy.platform_bootstrap.sync_deploy_platform_from_disk", return_value=None):
                    status = platform_automation_status(project)
        self.assertIn("masterKey", status)
        self.assertFalse(status["railway"]["hasToken"])

    @override_settings(VAULT_MASTER_KEY="c" * 64)
    def test_automate_project_deploy_runs_preflight(self):
        User = get_user_model()
        user = User(email="bootstrap@test.local")
        project = Project(owner=user, name="SilverFox", slug="silverfox", scan_data={"deployPlatform": "railway"})
        with patch("apps.deploy.platform_bootstrap.hydrate_project_vault", return_value=[]):
            with patch("apps.stripe_installer.hub_keys.pull_stripe_keys_for_user", return_value=[]):
                with patch("apps.deploy.platform_bootstrap.sync_deploy_platform_from_disk", return_value="railway"):
                    with patch("apps.deploy.preflight.run_deploy_preflight") as mock_preflight:
                        mock_preflight.return_value = {
                            "ok": False,
                            "issues": ["RAILWAY_API_TOKEN missing"],
                            "warnings": [],
                            "platform": "railway",
                            "railway": {},
                        }
                        result = automate_project_deploy(project, user=user)
        self.assertFalse(result["ok"])
        self.assertTrue(any(s["step"] == "preflight" for s in result["steps"]))
