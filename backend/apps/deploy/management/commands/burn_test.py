"""Burn test — exercise vault, env merge, scan_data, and preflight without live Railway pushes."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test.utils import override_settings

from apps.deploy.env_push import build_env_var_payload, merge_service_env_vars, push_to_railway
from apps.deploy.platform import detect_deploy_platform
from apps.deploy.preflight import run_deploy_preflight
from apps.projects.models import Project
from apps.projects.scan_data_utils import merge_scan_patch, update_project_scan_data
from apps.vault.models import (
    clear_project_vault,
    get_secret,
    get_or_create_vault,
    set_secret,
    vault_health,
)


class Command(BaseCommand):
    help = "Burn-test deployment automation (local, no live Railway mutations)"

    def handle(self, *args, **options):
        passed = 0
        failed = 0

        def check(name: str, fn) -> None:
            nonlocal passed, failed
            try:
                fn()
                self.stdout.write(self.style.SUCCESS(f"  PASS  {name}"))
                passed += 1
            except AssertionError as exc:
                self.stdout.write(self.style.ERROR(f"  FAIL  {name}: {exc}"))
                failed += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  FAIL  {name}: {type(exc).__name__}: {exc}"))
                failed += 1

        self.stdout.write("Burn test — vault lifecycle")
        check("vault encrypt/decrypt roundtrip", self._test_vault_roundtrip)
        check("clear vault removes DB + local backup", self._test_clear_vault)

        self.stdout.write("\nBurn test — env push merge")
        check("merge preserves unrelated Railway keys", self._test_env_merge)
        check("preset keeps Railway Postgres reference", self._test_database_url_reference)

        self.stdout.write("\nBurn test — scan_data")
        check("nested scan_data merge", self._test_scan_merge)
        check("atomic scan_data update", self._test_scan_atomic)

        self.stdout.write("\nBurn test — platform detection")
        check("railway.toml detected", self._test_platform_railway)
        check("preflight catches missing token", self._test_preflight_missing_token)
        check("preflight warns on empty Railway project list", self._test_preflight_empty_railway)

        self.stdout.write("\nBurn test — mocked Railway push")
        check("push merges with existing vars (mocked)", self._test_mocked_railway_push)

        self.stdout.write("")
        if failed:
            self.stdout.write(self.style.ERROR(f"Burn test: {passed} passed, {failed} failed"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"Burn test: {passed} passed, 0 failed"))

    @staticmethod
    @override_settings(VAULT_MASTER_KEY="a" * 64)
    def _test_vault_roundtrip() -> None:
        User = get_user_model()
        user, _ = User.objects.get_or_create(email="burn@test.local", defaults={"display_name": "Burn"})
        project, _ = Project.objects.get_or_create(
            owner=user,
            slug="burn-vault-test",
            defaults={"name": "Burn Vault", "local_path": str(Path.cwd())},
        )
        get_or_create_vault(project)
        set_secret(project, "BURN_KEY", "burn-secret-value-12345")
        assert get_secret(project, "BURN_KEY") == "burn-secret-value-12345"
        health = vault_health(project)
        assert health["unreadableCount"] == 0

    @staticmethod
    @override_settings(VAULT_MASTER_KEY="b" * 64)
    def _test_clear_vault() -> None:
        from apps.vault.local_store import local_vault_path

        User = get_user_model()
        user, _ = User.objects.get_or_create(email="burn@test.local", defaults={"display_name": "Burn"})
        project, _ = Project.objects.get_or_create(
            owner=user,
            slug="burn-clear-test",
            defaults={"name": "Burn Clear", "local_path": str(Path.cwd())},
        )
        set_secret(project, "TO_CLEAR", "x")
        assert local_vault_path(project.slug).is_file()
        clear_project_vault(project)
        assert get_secret(project, "TO_CLEAR") is None
        assert not local_vault_path(project.slug).is_file()

    @staticmethod
    def _test_env_merge() -> None:
        merged = merge_service_env_vars({"KEEP": "yes", "OLD": "1"}, {"OLD": "2", "NEW": "3"})
        assert merged["KEEP"] == "yes" and merged["OLD"] == "2" and merged["NEW"] == "3"

    @staticmethod
    @override_settings(VAULT_MASTER_KEY="c" * 64)
    def _test_database_url_reference() -> None:
        User = get_user_model()
        user, _ = User.objects.get_or_create(email="burn@test.local", defaults={"display_name": "Burn"})
        project, _ = Project.objects.get_or_create(
            owner=user,
            slug="burn-env-test",
            defaults={"name": "Burn Env", "local_path": str(Path.cwd())},
        )
        set_secret(project, "DATABASE_URL", "postgresql://user:pass@external/db")
        payload = build_env_var_payload(project, preset="silverfox")
        assert payload["DATABASE_URL"] == "${{Postgres.DATABASE_URL}}"

    @staticmethod
    def _test_scan_merge() -> None:
        merged = merge_scan_patch(
            {"railway": {"projectId": "p1", "lastEnvPushAt": "old"}},
            {"railway": {"serviceId": "s1", "lastEnvPushAt": "new"}},
        )
        assert merged["railway"]["projectId"] == "p1"
        assert merged["railway"]["serviceId"] == "s1"
        assert merged["railway"]["lastEnvPushAt"] == "new"

    @staticmethod
    def _test_scan_atomic() -> None:
        User = get_user_model()
        user, _ = User.objects.get_or_create(email="burn@test.local", defaults={"display_name": "Burn"})
        project, _ = Project.objects.get_or_create(
            owner=user,
            slug="burn-scan-test",
            defaults={"name": "Burn Scan", "local_path": str(Path.cwd()), "scan_data": {}},
        )
        update_project_scan_data(project, {"railway": {"projectId": "abc"}})
        project.refresh_from_db()
        assert project.scan_data["railway"]["projectId"] == "abc"

    @staticmethod
    def _test_platform_railway() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "railway.toml").write_text("[build]\n", encoding="utf-8")
            assert detect_deploy_platform(root, "django") == "railway"

    @staticmethod
    @override_settings(VAULT_MASTER_KEY="d" * 64)
    def _test_preflight_missing_token() -> None:
        User = get_user_model()
        user, _ = User.objects.get_or_create(email="burn@test.local", defaults={"display_name": "Burn"})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "railway.toml").write_text("", encoding="utf-8")
            project, _ = Project.objects.get_or_create(
                owner=user,
                slug="burn-preflight-token",
                defaults={
                    "name": "Burn Preflight",
                    "local_path": str(root),
                    "scan_data": {"deployPlatform": "railway"},
                },
            )
            project.local_path = str(root)
            project.scan_data = {"deployPlatform": "railway"}
            project.save(update_fields=["local_path", "scan_data", "updated_at"])
            clear_project_vault(project)
            result = run_deploy_preflight(project, push_railway_env=True, provision_stripe=False)
            assert not result["ok"]
            assert any("RAILWAY_API_TOKEN" in i for i in result["issues"])

    @staticmethod
    @override_settings(VAULT_MASTER_KEY="e" * 64)
    def _test_preflight_empty_railway() -> None:
        User = get_user_model()
        user, _ = User.objects.get_or_create(email="burn@test.local", defaults={"display_name": "Burn"})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "railway.toml").write_text("", encoding="utf-8")
            project, _ = Project.objects.get_or_create(
                owner=user,
                slug="burn-preflight-empty",
                defaults={
                    "name": "Burn Empty Railway",
                    "local_path": str(root),
                    "scan_data": {"deployPlatform": "railway"},
                },
            )
            project.local_path = str(root)
            project.scan_data = {"deployPlatform": "railway"}
            project.save(update_fields=["local_path", "scan_data", "updated_at"])
            set_secret(project, "RAILWAY_API_TOKEN", "fake-token-for-burn-test")
            with patch("apps.deploy.preflight.resolve_railway_project_id", return_value=None):
                with patch("apps.deploy.preflight._list_railway_projects", return_value=[]):
                    result = run_deploy_preflight(project, push_railway_env=True, provision_stripe=False)
            assert any("returned no projects" in w for w in result["warnings"])

    @staticmethod
    def _test_mocked_railway_push() -> None:
        existing = {"MANUAL_VAR": "keep", "STRIPE_SECRET_KEY": "old"}
        incoming = {"STRIPE_SECRET_KEY": "new", "DEBUG": "False"}

        with patch("apps.deploy.env_push.get_railway_env_vars", return_value=existing):
            with patch("apps.deploy.env_push._railway_gql") as mock_gql:
                push_to_railway("token", "proj", "svc", incoming, "env", preserve_existing=True)
                mock_gql.assert_called_once()
                sent = mock_gql.call_args[0][2]["input"]["variables"]
                assert sent["MANUAL_VAR"] == "keep"
                assert sent["STRIPE_SECRET_KEY"] == "new"
                assert sent["DEBUG"] == "False"
