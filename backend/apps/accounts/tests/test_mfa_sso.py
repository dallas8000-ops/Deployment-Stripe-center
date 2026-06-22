from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.mfa import (
    encrypt_mfa_secret,
    generate_recovery_codes,
    issue_mfa_challenge,
    verify_totp,
)

User = get_user_model()


@override_settings(
    VAULT_MASTER_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)
class MfaLoginFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="mfa-user@example.com",
            password="securepass123",
        )

    def test_login_without_mfa_returns_tokens(self):
        res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "mfa-user@example.com", "password": "securepass123"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)
        self.assertNotIn("mfa_required", res.data)

    def test_login_with_mfa_requires_second_step(self):
        secret = "JBSWY3DPEHPK3PXP"
        self.user.mfa_secret_encrypted = encrypt_mfa_secret(self.user.pk, secret)
        self.user.mfa_enabled = True
        self.user.save()

        res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "mfa-user@example.com", "password": "securepass123"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["mfa_required"])
        self.assertIn("mfa_token", res.data)

        import pyotp

        code = pyotp.TOTP(secret).now()
        verify = self.client.post(
            "/api/v1/auth/mfa/verify/",
            {"mfa_token": res.data["mfa_token"], "code": code},
            format="json",
        )
        self.assertEqual(verify.status_code, 200)
        self.assertIn("access", verify.data)

    def test_enroll_and_confirm_mfa(self):
        self.client.force_authenticate(user=self.user)
        start = self.client.post("/api/v1/auth/mfa/enroll/start/", {}, format="json")
        self.assertEqual(start.status_code, 200)
        secret = start.data["secret"]

        import pyotp

        confirm = self.client.post(
            "/api/v1/auth/mfa/enroll/confirm/",
            {"code": pyotp.TOTP(secret).now()},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertTrue(confirm.data["mfa_enabled"])
        self.assertEqual(len(confirm.data["recovery_codes"]), 10)

        self.user.refresh_from_db()
        self.assertTrue(self.user.mfa_enabled)


class MfaUnitTests(TestCase):
    def test_verify_totp_accepts_valid_code(self):
        secret = "JBSWY3DPEHPK3PXP"
        import pyotp

        code = pyotp.TOTP(secret).now()
        self.assertTrue(verify_totp(secret, code))

    def test_recovery_codes_hash_unique(self):
        plain, hashed = generate_recovery_codes()
        self.assertEqual(len(plain), len(hashed))
        self.assertEqual(len(set(hashed)), len(hashed))


@override_settings(
    OIDC_SSO_ENABLED=True,
    OIDC_ISSUER_URL="https://idp.example.com",
    OIDC_CLIENT_ID="client-id",
    OIDC_CLIENT_SECRET="client-secret",
    APP_PUBLIC_URL="http://localhost:5173",
)
class SsoConfigTests(TestCase):
    def test_sso_config_enabled(self):
        client = APIClient()
        res = client.get("/api/v1/auth/sso/config/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["enabled"])

    @patch("apps.accounts.views.build_authorize_url", return_value="https://idp.example.com/authorize")
    def test_sso_login_redirects(self, _mock):
        client = APIClient()
        res = client.get("/api/v1/auth/sso/login/")
        self.assertEqual(res.status_code, 302)
