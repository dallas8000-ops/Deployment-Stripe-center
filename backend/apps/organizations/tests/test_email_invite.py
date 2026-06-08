from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.organizations.invites import invite_register_url, invite_to_org
from apps.organizations.models import Membership, Organization, OrganizationInvite

User = get_user_model()


@override_settings(SAAS_STRIPE_SECRET_KEY="", INVITE_EMAIL_ENABLED=False)
class EmailInviteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(email="owner@test.com", password="pass12345")
        self.org = Organization.objects.create(name="Agency", slug="agency", created_by=self.owner)
        Membership.objects.create(organization=self.org, user=self.owner, role=Membership.Role.OWNER)
        self.client.force_authenticate(user=self.owner)

    def test_invite_new_user_creates_pending(self):
        result = invite_to_org(self.org, email="new@test.com", role="member", invited_by=self.owner)
        self.assertEqual(result["status"], "pending")
        self.assertTrue(OrganizationInvite.objects.filter(email="new@test.com").exists())

    def test_register_with_invite_joins_org(self):
        result = invite_to_org(self.org, email="join@test.com", role="admin", invited_by=self.owner)
        token = result["invite"].token
        res = self.client.post(
            "/api/v1/auth/register/",
            {
                "email": "join@test.com",
                "password": "pass12345",
                "display_name": "Joiner",
                "invite_token": token,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="join@test.com")
        membership = Membership.objects.get(organization=self.org, user=user)
        self.assertEqual(membership.role, Membership.Role.ADMIN)

    def test_invite_preview_public(self):
        result = invite_to_org(self.org, email="preview@test.com", role="member", invited_by=self.owner)
        url = f"/api/v1/invites/{result['invite'].token}/"
        anon = APIClient()
        res = anon.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["valid"])
        self.assertIn("/register?invite=", invite_register_url(result["invite"].token))
