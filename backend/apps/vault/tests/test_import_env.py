import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.projects.models import Project
from apps.vault.import_env import import_env_to_vault


class ImportEnvTests(SimpleTestCase):
    def test_imports_stripe_keys(self):
        project = Project(name="Test", slug="test")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                "STRIPE_SECRET_KEY=sk_test_abc\n"
                "STRIPE_PUBLISHABLE_KEY=pk_test_xyz\n"
                "IGNORED=1\n",
                encoding="utf-8",
            )
            with patch("apps.vault.import_env.set_secret") as mock_set:
                with patch("apps.vault.import_env.get_secret", return_value="pk_test_xyz"):
                    imported = import_env_to_vault(project, root, ".env.local")
            self.assertIn("STRIPE_SECRET_KEY", imported)
            self.assertIn("STRIPE_PUBLISHABLE_KEY", imported)
            self.assertIn("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", imported)
            self.assertEqual(mock_set.call_count, 3)
