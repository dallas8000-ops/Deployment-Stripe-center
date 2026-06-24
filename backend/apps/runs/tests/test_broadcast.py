from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.projects.models import Project
from apps.runs.broadcast import make_run_emitter, run_group_name
from apps.runs.models import PipelineRun, PipelineRunLog
from apps.stripe_core.events import PipelineEvent

User = get_user_model()


class BroadcastTests(TestCase):
    def test_run_group_name(self):
        self.assertEqual(run_group_name("abc-123"), "pipeline_run_abc-123")

    @override_settings(CHANNEL_LAYER_INMEMORY=True)
    def test_emitter_persists_log(self):
        user = User.objects.create_user(email="runs@test.local", password="pass12345")
        project = Project.objects.create(owner=user, name="Runs", slug="runs-test")
        run = PipelineRun.objects.create(project=project, started_by=user)

        emit = make_run_emitter(run)
        emit(
            PipelineEvent(
                step="scan",
                status="ok",
                message="Scan complete",
                detail=False,
                score=90,
            )
        )

        logs = list(PipelineRunLog.objects.filter(run=run))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].step, "scan")
        self.assertEqual(logs[0].score, 90)
