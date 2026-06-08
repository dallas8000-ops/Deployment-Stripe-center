import json

from django.test import Client, TestCase

from apps.licenses.models import License


class LicenseValidateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.license = License.objects.create(
            key="test-license-key-abc",
            customer_email="buyer@test.com",
            registered_domain="app.example.com",
            stripe_subscription_id="sub_test",
            max_instances=1,
            status=License.Status.ACTIVE,
        )

    def test_validate_success(self):
        resp = self.client.post(
            "/api/v1/license/validate/",
            data=json.dumps(
                {
                    "license_key": self.license.key,
                    "domain": "app.example.com",
                    "instance_id": "inst-001",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["max_instances"], 1)

    def test_validate_domain_mismatch(self):
        resp = self.client.post(
            "/api/v1/license/validate/",
            data=json.dumps(
                {
                    "license_key": self.license.key,
                    "domain": "other.example.com",
                    "instance_id": "inst-002",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()["valid"])

    def test_validate_localhost_dev(self):
        dev = License.objects.create(
            key="dev-local-key",
            customer_email="dev@test.com",
            registered_domain="localhost",
            stripe_subscription_id="sub_dev",
            max_instances=1,
        )
        resp = self.client.post(
            "/api/v1/license/validate/",
            data=json.dumps(
                {"license_key": dev.key, "domain": "localhost", "instance_id": "inst-dev"}
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["valid"])
