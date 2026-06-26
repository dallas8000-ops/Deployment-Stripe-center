from django.test import SimpleTestCase

from apps.deploy.railway_deploy import github_repo_slug
from apps.projects.models import Project


class RailwayDeployTests(SimpleTestCase):
    def test_github_repo_slug_from_git_url(self):
        project = Project(git_url="https://github.com/dallas8000-ops/AgriPay-Logistics-AI.git")
        self.assertEqual(github_repo_slug(project), "dallas8000-ops/AgriPay-Logistics-AI")

    def test_github_repo_slug_missing(self):
        project = Project(git_url="")
        self.assertIsNone(github_repo_slug(project))
