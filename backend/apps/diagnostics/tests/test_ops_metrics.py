from django.test import TestCase, override_settings

from apps.diagnostics.ops_metrics import collect_ops_metrics


@override_settings(DEBUG=True, CELERY_TASK_ALWAYS_EAGER=True)
class OpsMetricsTests(TestCase):
    def test_collect_ops_metrics_shape(self):
        metrics = collect_ops_metrics()
        self.assertIn("timestamp", metrics)
        self.assertIn("version", metrics)
        self.assertIn("database", metrics)
        self.assertIn("transfer_runs", metrics)
        self.assertEqual(metrics["transfer_queue_depth"], 0)
