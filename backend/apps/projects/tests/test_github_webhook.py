from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.projects.github_webhook import find_project_for_repo, verify_github_signature
from apps.projects.models import Project


class GithubWebhookSignatureTests(TestCase):
    @override_settings(GITHUB_WEBHOOK_SECRET="test-secret")
    def test_verify_signature_valid(self):
        import hashlib
        import hmac

        payload = b'{"ok":true}'
        digest = hmac.new(b"test-secret", payload, hashlib.sha256).hexdigest()
        self.assertTrue(verify_github_signature(payload, f"sha256={digest}"))

    @override_settings(GITHUB_WEBHOOK_SECRET="test-secret")
    def test_verify_signature_invalid(self):
        self.assertFalse(verify_github_signature(b"{}", "sha256=bad"))


class FindProjectForRepoTests(TestCase):
    def test_find_project_for_repo(self):
        user = get_user_model().objects.create_user(email="gh@test.com", password="pass12345")
        project = Project.objects.create(
            owner=user,
            name="App",
            slug="app",
            git_url="https://github.com/acme/payments-api",
        )
        found = find_project_for_repo("acme", "payments-api")
        self.assertEqual(found.id, project.id)
