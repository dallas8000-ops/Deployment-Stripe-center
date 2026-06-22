from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.diagnostics.drift import DriftItem, persist_drift_snapshot
from apps.projects.models import Project

User = get_user_model()


class DriftTests(TestCase):
    def test_drift_item_serializes(self):
        item = DriftItem("webhook", "warning", "missing", "fix it")
        self.assertEqual(
            item.to_dict(),
            {"category": "webhook", "severity": "warning", "message": "missing", "fix": "fix it"},
        )

    def test_persist_drift_snapshot_updates_scan_data(self):
        user = User.objects.create_user(email="drift@test.local", password="pass12345")
        project = Project.objects.create(owner=user, name="Drift", slug="drift-test", scan_data={})
        result = {
            "driftCount": 1,
            "checkedAt": "2026-01-01T00:00:00+00:00",
            "manifestPriceCount": 0,
            "items": [{"category": "webhook", "severity": "warning", "message": "x", "fix": "y"}],
        }
        persist_drift_snapshot(project, result)
        project.refresh_from_db()
        self.assertEqual(project.scan_data["lastDrift"]["driftCount"], 1)
