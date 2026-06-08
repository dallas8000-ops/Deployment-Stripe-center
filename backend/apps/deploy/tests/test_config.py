from django.test import SimpleTestCase

from apps.deploy.config import normalize_deploy_config, write_deploy_config, read_deploy_config


class DeployConfigTests(SimpleTestCase):
    def test_normalize_domain_to_production_url(self):
        cfg = normalize_deploy_config({"domain": "app.example.com"})
        self.assertEqual(cfg["productionUrl"], "https://app.example.com")

    def test_invalid_platform_raises(self):
        with self.assertRaises(ValueError):
            normalize_deploy_config({"platform": "heroku"})

    def test_write_and_read_roundtrip(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_deploy_config(
                root,
                {
                    "productionUrl": "https://app.test",
                    "platform": "vercel",
                    "postgres": {"provider": "neon", "autoProvision": False},
                },
            )
            raw = read_deploy_config(root)
            self.assertEqual(raw["productionUrl"], "https://app.test")
            self.assertEqual(raw["platform"], "vercel")
            self.assertFalse(raw["postgres"]["autoProvision"])
