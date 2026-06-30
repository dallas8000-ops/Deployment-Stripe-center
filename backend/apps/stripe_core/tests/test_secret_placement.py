from django.test import TestCase

from apps.stripe_core.secret_placement import _classify_live_probe, _key_format, _normalize_url


class SecretPlacementHelpersTests(TestCase):
    def test_key_format_webhook_rejects_sk_prefix(self):
        ok, msg = _key_format("STRIPE_WEBHOOK_SECRET", "sk_live_abc")
        self.assertFalse(ok)
        self.assertIn("sk_", msg)

    def test_key_format_webhook_accepts_whsec(self):
        ok, msg = _key_format("STRIPE_WEBHOOK_SECRET", "whsec_test123456789")
        self.assertTrue(ok)
        self.assertEqual(msg, "whsec_ok")

    def test_normalize_url_strips_trailing_slash(self):
        self.assertEqual(_normalize_url("https://example.com/hook/"), "https://example.com/hook")

    def test_classify_csrf_probe(self):
        body = "<title>403 Forbidden</title> CSRF verification failed"
        self.assertEqual(_classify_live_probe(403, body), "csrf_blocked")

    def test_classify_signature_probe(self):
        self.assertEqual(_classify_live_probe(400, "Invalid payload"), "signature_check_active")
