from unittest.mock import patch

from django.test import SimpleTestCase

from apps.deploy.provision import _provision_self_hosted
from apps.projects.models import Project


class SelfHostedProvisionTests(SimpleTestCase):
    def test_requires_database_url(self):
        project = Project(name="Test", slug="test")
        with patch("apps.deploy.provision.get_secret", return_value=None):
            with self.assertRaises(RuntimeError):
                _provision_self_hosted(project)
