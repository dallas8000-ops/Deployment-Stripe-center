from unittest.mock import patch

from django.test import SimpleTestCase

from apps.projects.git_clone import _authenticated_url, parse_github_repo, validate_git_url
from apps.projects.models import Project


class GitAuthTests(SimpleTestCase):
    def test_authenticated_github_url_no_token(self):
        project = Project(name="x", slug="x")
        url = "https://github.com/org/repo.git"
        with patch("apps.projects.git_clone._resolve_git_token", return_value=None):
            auth = _authenticated_url(url, project)
        self.assertEqual(url, auth)

    def test_authenticated_github_url_with_token(self):
        project = Project(name="x", slug="x")
        url = "https://github.com/org/repo.git"
        with patch("apps.projects.git_clone._resolve_git_token", return_value="ghp_test"):
            auth = _authenticated_url(url, project)
        self.assertIn("x-access-token:", auth)
        self.assertIn("github.com", auth)

    def test_parse_github_https(self):
        self.assertEqual(
            parse_github_repo("https://github.com/acme/app.git"),
            ("acme", "app"),
        )

    def test_validate_rejects_invalid(self):
        with self.assertRaises(ValueError):
            validate_git_url("ftp://bad")
