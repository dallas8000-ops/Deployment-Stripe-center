from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization

User = get_user_model()


class MemberPatchTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(email="owner@test.com", password="pass12345")
        self.member = User.objects.create_user(email="member@test.com", password="pass12345")
        self.org = Organization.objects.create(name="GitHub Org", slug="github", created_by=self.owner)
        Membership.objects.create(organization=self.org, user=self.owner, role=Membership.Role.OWNER)
        self.membership = Membership.objects.create(
            organization=self.org, user=self.member, role=Membership.Role.MEMBER
        )
        self.client.force_authenticate(user=self.owner)

    def test_patch_member_role(self):
        url = f"/api/v1/organizations/github/members/{self.membership.id}/"
        res = self.client.patch(url, {"role": "admin"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, Membership.Role.ADMIN)

    def test_delete_member(self):
        url = f"/api/v1/organizations/github/members/{self.membership.id}/"
        res = self.client.delete(url)
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Membership.objects.filter(id=self.membership.id).exists())
