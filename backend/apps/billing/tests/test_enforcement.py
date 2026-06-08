from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.billing.enforcement import (
    BillingLimitError,
    assert_can_add_org_member,
    assert_can_assign_org_project,
)
from apps.organizations.models import Membership, Organization

User = get_user_model()


@override_settings(SAAS_STRIPE_SECRET_KEY="sk_test_fake")
class OrgBillingEnforcementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@test.com", password="pass12345")
        self.org = Organization.objects.create(name="Agency", slug="agency", created_by=self.owner)
        Membership.objects.create(organization=self.org, user=self.owner, role=Membership.Role.OWNER)

    @override_settings(ORG_FREE_MEMBER_LIMIT="2")
    def test_member_limit_blocks_invite(self):
        User.objects.create_user(email="a@test.com", password="pass12345")
        User.objects.create_user(email="b@test.com", password="pass12345")
        Membership.objects.create(organization=self.org, user=User.objects.get(email="a@test.com"), role="member")
        with self.assertRaises(BillingLimitError):
            assert_can_add_org_member(self.org)

    @override_settings(ORG_FREE_PROJECT_LIMIT="1")
    def test_project_limit_blocks_assign(self):
        from apps.projects.models import Project

        Project.objects.create(owner=self.owner, organization=self.org, name="P1", slug="p1")
        with self.assertRaises(BillingLimitError):
            assert_can_assign_org_project(self.org)

    @override_settings(SAAS_STRIPE_SECRET_KEY="")
    def test_exempt_when_saas_not_configured(self):
        assert_can_add_org_member(self.org) is None
