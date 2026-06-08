from django.test import SimpleTestCase

from apps.projects.git_clone import validate_git_url


class GitCloneValidationTests(SimpleTestCase):
    def test_accepts_https(self):
        self.assertEqual(validate_git_url("https://github.com/org/repo.git"), "https://github.com/org/repo.git")

    def test_rejects_invalid(self):
        with self.assertRaises(ValueError):
            validate_git_url("not-a-url")
