from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.projects.models import Project


class ProjectCreateTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="project-create@example.com",
            password="test-pass-123",
        )
        self.client.force_authenticate(self.user)

    @patch("apps.deploy.platform_bootstrap.bootstrap_new_project")
    def test_create_preserves_external_local_path(self, bootstrap):
        local_path = r"C:\Software Projects\External Sample App"

        response = self.client.post(
            "/api/v1/projects/",
            {"name": "External Sample App", "local_path": local_path},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["local_path"], local_path)
        self.assertEqual(Project.objects.get(owner=self.user).local_path, local_path)
        bootstrap.assert_called_once()

    def test_create_rejects_path_inside_automation_center(self):
        local_path = str(Path(settings.REPO_ROOT) / "nested-project")

        response = self.client.post(
            "/api/v1/projects/",
            {"name": "Nested App", "local_path": local_path},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("local_path", response.data)
        self.assertFalse(Project.objects.filter(owner=self.user).exists())
