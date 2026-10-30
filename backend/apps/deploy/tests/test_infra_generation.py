"""Regression tests: generated deploy configs must never ship a guessed start command.

History: every Django app received ``gunicorn myproject.wsgi`` (a module that does not
exist), and monorepos received a root railway.toml that overrode every Railway
service's build (broke Specwright's frontend twice).
"""
import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.deploy.infra import generate_infra_files, railway_config_skip_reason
from apps.deploy.platform import (
    framework_start_command,
    generate_dockerfile,
    resolve_django_wsgi_module,
)

MANAGE_PY = (
    "import os, sys\n"
    "def main():\n"
    "    os.environ.setdefault('DJANGO_SETTINGS_MODULE', '{settings}')\n"
)


def _django_app(root: Path, settings: str = "config.settings", pkg: str = "config") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manage.py").write_text(MANAGE_PY.format(settings=settings), encoding="utf-8")
    (root / pkg).mkdir(parents=True, exist_ok=True)
    (root / pkg / "wsgi.py").write_text("application = None\n", encoding="utf-8")


def _project(root: Path, framework: str = "django", **scan) -> SimpleNamespace:
    scan.setdefault("deployPlatform", "railway")
    return SimpleNamespace(slug="t", framework=framework, local_path=str(root), scan_data=scan)


class ResolveWsgiModuleTests(SimpleTestCase):
    def test_reads_settings_module_from_manage_py(self):
        with tempfile.TemporaryDirectory() as tmp:
            _django_app(Path(tmp), settings="config.settings", pkg="config")
            self.assertEqual(resolve_django_wsgi_module(Path(tmp)), "config.wsgi")

    def test_split_settings_package_walks_up_to_wsgi(self):
        with tempfile.TemporaryDirectory() as tmp:
            _django_app(Path(tmp), settings="core.settings.production", pkg="core")
            self.assertEqual(resolve_django_wsgi_module(Path(tmp)), "core.wsgi")

    def test_single_wsgi_fallback_without_manage_py(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shop").mkdir()
            (Path(tmp) / "shop" / "wsgi.py").write_text("", encoding="utf-8")
            self.assertEqual(resolve_django_wsgi_module(Path(tmp)), "shop.wsgi")

    def test_ambiguous_or_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            for pkg in ("a", "b"):
                (Path(tmp) / pkg).mkdir()
                (Path(tmp) / pkg / "wsgi.py").write_text("", encoding="utf-8")
            self.assertIsNone(resolve_django_wsgi_module(Path(tmp)))


class StartCommandTests(SimpleTestCase):
    def test_django_without_module_has_no_default(self):
        self.assertIsNone(framework_start_command("django"))
        self.assertIsNone(generate_dockerfile("django"))

    def test_django_uses_resolved_module(self):
        self.assertEqual(
            framework_start_command("django", wsgi_module="config.wsgi"),
            "gunicorn config.wsgi:application --bind 0.0.0.0:$PORT",
        )
        dockerfile = generate_dockerfile("django", wsgi_module="config.wsgi")
        self.assertIn("CMD gunicorn config.wsgi:application --bind 0.0.0.0:${PORT}", dockerfile)

    def test_other_frameworks_unchanged(self):
        self.assertEqual(framework_start_command("nextjs"), "npm run start")
        self.assertEqual(framework_start_command("flask"), "gunicorn app:app --bind 0.0.0.0:$PORT")


class GenerateInfraFilesTests(SimpleTestCase):
    PROD = "https://example.up.railway.app"

    def test_root_django_app_gets_correct_railway_toml_and_dockerfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _django_app(root)
            (root / "requirements.txt").write_text("django\n", encoding="utf-8")
            files = generate_infra_files(_project(root), root, prod_url=self.PROD)
        self.assertIn('startCommand = "gunicorn config.wsgi:application', files["railway.toml"])
        self.assertIn("gunicorn config.wsgi:application", files["Dockerfile"])
        self.assertFalse(any("myproject" in content for content in files.values()))

    def test_monorepo_gets_no_root_railway_toml_or_dockerfile(self):
        """Specwright layout: backend/manage.py + config package, separate Railway services."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _django_app(root / "backend")
            (root / "frontend").mkdir()
            files = generate_infra_files(_project(root), root, prod_url=self.PROD)
        self.assertNotIn("railway.toml", files)
        self.assertNotIn("Dockerfile", files)
        self.assertIn("db/schema.sql", files)  # the rest of the infra bundle is still produced

    def test_unresolvable_wsgi_skips_platform_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manage.py").write_text("print('no settings here')\n", encoding="utf-8")
            (root / "requirements.txt").write_text("django\n", encoding="utf-8")
            files = generate_infra_files(_project(root), root, prod_url=self.PROD)
        self.assertNotIn("railway.toml", files)
        self.assertNotIn("Dockerfile", files)

    def test_nextjs_root_app_still_gets_railway_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text("{}", encoding="utf-8")
            files = generate_infra_files(_project(root, framework="nextjs"), root, prod_url=self.PROD)
        self.assertIn('startCommand = "npm run start"', files["railway.toml"])


class RailwaySkipReasonTests(SimpleTestCase):
    def test_existing_config_in_service_dir_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend").mkdir()
            (root / "backend" / "railway.json").write_text("{}", encoding="utf-8")
            reason = railway_config_skip_reason(_project(root), root, "backend", "gunicorn x.wsgi:application")
        self.assertIn("backend/railway.json", reason)

    def test_missing_root_requirements_blocks_python_build_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reason = railway_config_skip_reason(_project(root), root, "", "gunicorn x.wsgi:application")
        self.assertIn("requirements.txt", reason)

    def test_safe_single_service_app_has_no_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements.txt").write_text("django\n", encoding="utf-8")
            self.assertIsNone(railway_config_skip_reason(_project(root), root, "", "gunicorn x.wsgi:application"))
