from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.access import get_project_for_user, projects_for_user
from apps.organizations.models import Membership, Organization
from apps.projects.models import Project

User = get_user_model()


class OrganizationAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@test.com", password="pass12345")
        self.member = User.objects.create_user(email="member@test.com", password="pass12345")
        self.outsider = User.objects.create_user(email="other@test.com", password="pass12345")
        self.org = Organization.objects.create(name="Agency", slug="agency", created_by=self.owner)
        Membership.objects.create(organization=self.org, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(organization=self.org, user=self.member, role=Membership.Role.MEMBER)
        self.project = Project.objects.create(
            owner=self.owner,
            organization=self.org,
            name="Client App",
            slug="client-app",
        )

    def test_member_can_access_org_project(self):
        project = get_project_for_user(self.member, "client-app", min_role="viewer")
        self.assertEqual(project.slug, "client-app")

    def test_outsider_cannot_access_org_project(self):
        from django.http import Http404

        with self.assertRaises(Http404):
            get_project_for_user(self.outsider, "client-app")

    def test_projects_for_user_includes_org(self):
        slugs = set(projects_for_user(self.member).values_list("slug", flat=True))
        self.assertIn("client-app", slugs)
