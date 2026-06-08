from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from apps.deploy.config import normalize_deploy_config, resolve_production_url
from apps.projects.models import Project

User = get_user_model()


class EnvironmentUrlTests(SimpleTestCase):
    def test_normalize_environments(self):
        cfg = normalize_deploy_config(
            {
                "environments": {
                    "staging": {"url": "https://staging.example.com"},
                    "production": {"url": "https://app.example.com"},
                }
            }
        )
        self.assertEqual(cfg["environments"]["staging"]["url"], "https://staging.example.com")

    def test_resolve_active_environment_url(self):
        user = User(email="t@example.com")
        project = Project(
            name="Demo",
            slug="demo",
            owner=user,
            scan_data={"activeEnvironment": "staging"},
        )
        from pathlib import Path
        from unittest.mock import patch

        root = Path("/tmp/fake")
        with patch("apps.deploy.config.read_deploy_config") as mock_read:
            mock_read.return_value = {
                "productionUrl": "https://prod.example.com",
                "environments": {
                    "staging": {"url": "https://staging.example.com"},
                    "production": {"url": "https://prod.example.com"},
                },
            }
            with patch.object(Path, "is_dir", return_value=True):
                url = resolve_production_url(project, root, "")
        self.assertEqual(url, "https://staging.example.com")
