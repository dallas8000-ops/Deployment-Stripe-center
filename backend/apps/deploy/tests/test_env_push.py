from django.test import SimpleTestCase

from apps.deploy.env_push import KISTIE_STORE_PRESET, merge_env_vars


class EnvPushMergeTests(SimpleTestCase):
    def test_inline_overrides_preset(self):
        merged = merge_env_vars(
            preset={"SITE_URL": "https://old.example.com", "DJANGO_DEBUG": "False"},
            inline={"SITE_URL": "https://kistie-store-production.up.railway.app"},
        )
        self.assertEqual(merged["SITE_URL"], "https://kistie-store-production.up.railway.app")
        self.assertEqual(merged["DJANGO_DEBUG"], "False")

    def test_vault_overrides_preset(self):
        merged = merge_env_vars(
            preset={"DATABASE_URL": "${{Postgres.DATABASE_URL}}"},
            vault={"DATABASE_URL": "postgresql://real"},
        )
        self.assertEqual(merged["DATABASE_URL"], "postgresql://real")

    def test_kistie_preset_excludes_portfolio_domain(self):
        self.assertNotIn("gilliomfrontlinedigital.com", KISTIE_STORE_PRESET.get("SITE_URL", ""))
        self.assertIn("kistie-store-production", KISTIE_STORE_PRESET["SITE_URL"])
