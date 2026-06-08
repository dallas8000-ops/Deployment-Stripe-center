from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization

User = get_user_model()


@override_settings(GITHUB_APP_SLUG="stripe-installer-test")
class GithubInstallUrlTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(email="owner@test.com", password="pass12345")
        self.org = Organization.objects.create(name="Agency", slug="agency", created_by=self.owner)
        Membership.objects.create(organization=self.org, user=self.owner, role=Membership.Role.OWNER)
        self.client.force_authenticate(user=self.owner)

    def test_install_url_contains_slug_and_state(self):
        res = self.client.get("/api/v1/organizations/agency/github/install-url/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["configured"])
        self.assertIn("github.com/apps/stripe-installer-test/installations/new", data["url"])
        self.assertTrue(data["state"].startswith("agency:"))

    def test_complete_install_links_org(self):
        res = self.client.post(
            "/api/v1/organizations/agency/github/complete-install/",
            {"installation_id": 99999, "state": "agency:abc"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.github_installation_id, 99999)
