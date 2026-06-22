from django.test import SimpleTestCase

from apps.api_transfer.redaction import REDACTED, redact_sensitive_values


class RedactionTests(SimpleTestCase):
    def test_redacts_top_level_secrets(self):
        payload = {"apiKey": "secret-value", "name": "visible"}
        result = redact_sensitive_values(payload)
        self.assertEqual(result["apiKey"], REDACTED)
        self.assertEqual(result["name"], "visible")

    def test_redacts_nested_secrets(self):
        payload = {
            "config": {
                "stripe": {"webhook_secret": "whsec_123"},
                "region": "us-east-1",
            }
        }
        result = redact_sensitive_values(payload)
        self.assertEqual(result["config"]["stripe"]["webhook_secret"], REDACTED)
        self.assertEqual(result["config"]["region"], "us-east-1")

    def test_preserves_lists(self):
        payload = [{"token": "abc"}, {"label": "ok"}]
        result = redact_sensitive_values(payload)
        self.assertEqual(result[0]["token"], REDACTED)
        self.assertEqual(result[1]["label"], "ok")
