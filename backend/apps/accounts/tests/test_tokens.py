from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.tokens import issue_tokens_for_user

User = get_user_model()


class TokenIssueTests(TestCase):
    def test_issue_tokens_for_user(self):
        user = User.objects.create_user(email="token@test.local", password="pass12345")
        tokens = issue_tokens_for_user(user)
        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)
        self.assertTrue(len(tokens["access"]) > 20)
