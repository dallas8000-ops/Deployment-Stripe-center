from django.test import SimpleTestCase

from apps.deploy.env_push import (
    KISTIE_STORE_PRESET,
    SILVERFOX_PRESET,
    _apply_vault_overrides,
    is_placeholder_database_url,
    merge_env_vars,
    merge_service_env_vars,
)


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

    def test_silverfox_preset_uses_debug_not_django_debug(self):
        self.assertEqual(SILVERFOX_PRESET["DEBUG"], "False")
        self.assertNotIn("DJANGO_DEBUG", SILVERFOX_PRESET)
        self.assertIn("silverfox-production", SILVERFOX_PRESET["CSRF_TRUSTED_ORIGINS"])
        self.assertEqual(SILVERFOX_PRESET["DATABASE_URL"], "${{Postgres.DATABASE_URL}}")

    def test_vault_literal_db_does_not_override_railway_reference(self):
        preset = {"DATABASE_URL": "${{Postgres.DATABASE_URL}}", "DEBUG": "False"}
        vault = {"DATABASE_URL": "postgresql://user:pass@host/db"}
        filtered = _apply_vault_overrides(preset, vault)
        self.assertNotIn("DATABASE_URL", filtered)
        merged = merge_env_vars(preset=preset, vault=filtered)
        self.assertEqual(merged["DATABASE_URL"], "${{Postgres.DATABASE_URL}}")

    def test_merge_service_env_preserves_unrelated_keys(self):
        existing = {"SECRET_A": "keep", "SHARED": "old"}
        incoming = {"SHARED": "new", "SECRET_B": "added"}
        merged = merge_service_env_vars(existing, incoming)
        self.assertEqual(merged["SECRET_A"], "keep")
        self.assertEqual(merged["SHARED"], "new")
        self.assertEqual(merged["SECRET_B"], "added")

    def test_merge_service_env_skips_empty_overwrite(self):
        existing = {"SECRET": "keep-me"}
        merged = merge_service_env_vars(existing, {"SECRET": "  "})
        self.assertEqual(merged["SECRET"], "keep-me")

    def test_merge_service_env_preserves_working_database_url(self):
        existing = {
            "DATABASE_URL": "postgresql://postgres:secret@monorail.proxy.rlwy.net:6543/railway",
        }
        incoming = {"DATABASE_URL": "${{Postgres.DATABASE_URL}}", "DEBUG": "False"}
        merged = merge_service_env_vars(existing, incoming)
        self.assertEqual(merged["DATABASE_URL"], existing["DATABASE_URL"])
        self.assertEqual(merged["DEBUG"], "False")

    def test_merge_service_env_replaces_placeholder_database_url(self):
        existing = {"DATABASE_URL": "postgresql://user:pass@localhost:5432/yourdb"}
        incoming = {"DATABASE_URL": "${{Postgres.DATABASE_URL}}"}
        merged = merge_service_env_vars(existing, incoming)
        self.assertEqual(merged["DATABASE_URL"], "${{Postgres.DATABASE_URL}}")

    def test_placeholder_database_url_detector(self):
        self.assertTrue(is_placeholder_database_url("postgresql://user:pass@localhost:5432/yourdb"))
        self.assertFalse(
            is_placeholder_database_url("postgresql://postgres:secret@monorail.proxy.rlwy.net:6543/railway")
        )
