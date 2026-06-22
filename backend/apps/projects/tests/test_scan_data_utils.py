from django.test import SimpleTestCase

from apps.projects.scan_data_utils import merge_scan_patch


class ScanDataMergeTests(SimpleTestCase):
    def test_merge_nested_dicts(self):
        scan = {"railway": {"projectId": "p1", "lastEnvPushAt": "2024-01-01"}}
        patch = {"railway": {"serviceId": "s1", "lastEnvPushAt": "2024-06-01"}}
        merged = merge_scan_patch(scan, patch)
        self.assertEqual(merged["railway"]["projectId"], "p1")
        self.assertEqual(merged["railway"]["serviceId"], "s1")
        self.assertEqual(merged["railway"]["lastEnvPushAt"], "2024-06-01")

    def test_top_level_replace(self):
        scan = {"deployPlatform": "unknown"}
        merged = merge_scan_patch(scan, {"deployPlatform": "railway"})
        self.assertEqual(merged["deployPlatform"], "railway")
