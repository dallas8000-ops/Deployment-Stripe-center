from django.test import SimpleTestCase

from apps.stripe_core.codegen.paths import (
    codegen_backend_prefix,
    filter_infra_paths,
    relocate_codegen_paths,
)


class CodegenPathsTests(SimpleTestCase):
    def test_relocates_django_stripe_under_backend(self):
        files = {
            "stripe_billing/views.py": "views",
            "docs/STRIPE-DJANGO.md": "docs",
            "db/schema.sql": "schema",
        }
        out = relocate_codegen_paths(files, "django", "backend")
        self.assertEqual(out["backend/stripe_billing/views.py"], "views")
        self.assertEqual(out["docs/STRIPE-DJANGO.md"], "docs")
        self.assertEqual(out["db/schema.sql"], "schema")

    def test_no_relocate_without_prefix(self):
        files = {"stripe/views.py": "views"}
        out = relocate_codegen_paths(files, "django", "")
        self.assertEqual(out, files)

    def test_codegen_backend_prefix_from_scan_data(self):
        class P:
            framework = "django"
            scan_data = {"scanBackendPath": "backend"}

        self.assertEqual(codegen_backend_prefix(P(), __import__("pathlib").Path("/repo")), "backend")

    def test_filter_infra_skips_root_dockerfile_when_backend_has_one(self):
        import tempfile
        from pathlib import Path

        class P:
            framework = "django"
            scan_data = {"scanBackendPath": "backend"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend").mkdir()
            (root / "backend" / "Dockerfile").write_text("FROM python\n", encoding="utf-8")
            files = {
                "Dockerfile": "FROM python:3.12\n",
                "stripe_billing/health_views.py": "health",
            }
            out = filter_infra_paths(files, P(), root)
            self.assertNotIn("Dockerfile", out)
            self.assertEqual(out["backend/stripe_billing/health_views.py"], "health")
