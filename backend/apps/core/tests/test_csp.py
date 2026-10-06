"""Regression tests: production must send a Content-Security-Policy header.

django-csp >= 4.0 silently ignores the legacy CSP_* settings, which left the live
site with no CSP header at all. These tests fail if that happens again.
"""

from django.conf import settings
from django.core import checks
from django.test import SimpleTestCase, override_settings


class ContentSecurityPolicyTests(SimpleTestCase):
    def test_production_policy_is_sent(self):
        with override_settings(CONTENT_SECURITY_POLICY=settings.PRODUCTION_CSP):
            response = self.client.get("/csp-regression-probe/")
        header = response.headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", header)
        self.assertIn("script-src 'self'", header)
        self.assertIn("frame-ancestors 'none'", header)

    def test_no_legacy_csp_settings(self):
        legacy = [name for name in dir(settings) if name.startswith("CSP_") and name.endswith("_SRC")]
        self.assertEqual(legacy, [], "legacy django-csp 3.x settings are ignored by 4.x")

    def test_csp_system_checks_pass(self):
        errors = [e for e in checks.run_checks() if (e.id or "").startswith("csp.")]
        self.assertEqual(errors, [])
