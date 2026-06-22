from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.runs.consumers import get_run_for_user
from apps.projects.models import Project
from apps.runs.models import PipelineRun

User = get_user_model()


class RunAccessTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@test.local", password="pass12345")
        self.other = User.objects.create_user(email="other@test.local", password="pass12345")
        self.project = Project.objects.create(owner=self.owner, name="Owned", slug="owned-project")
        self.run = PipelineRun.objects.create(project=self.project, started_by=self.owner)

    def test_owner_can_access_run(self):
        run = async_to_sync(get_run_for_user)(str(self.run.id), self.owner.id)
        self.assertIsNotNone(run)
        self.assertEqual(str(run.id), str(self.run.id))

    def test_other_user_cannot_access_run(self):
        run = async_to_sync(get_run_for_user)(str(self.run.id), self.other.id)
        self.assertIsNone(run)
