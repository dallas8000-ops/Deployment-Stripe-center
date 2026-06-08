from django.test import TestCase

from apps.licenses.utils import normalize_domain, validate_domain_format


class LicenseUtilsTests(TestCase):
    def test_normalize_domain(self):
        self.assertEqual(normalize_domain("https://App.Example.com/path"), "app.example.com")
        self.assertEqual(normalize_domain("localhost:8000"), "localhost")

    def test_validate_localhost(self):
        self.assertTrue(validate_domain_format("localhost"))
        self.assertTrue(validate_domain_format("127.0.0.1"))

    def test_validate_production_domain(self):
        self.assertTrue(validate_domain_format("app.example.com"))
        self.assertFalse(validate_domain_format("not-a-domain"))
