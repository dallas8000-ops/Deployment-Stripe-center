from django.test import SimpleTestCase

from apps.deploy.railway_resolve import preset_for_project, _name_matches


class RailwayResolveTests(SimpleTestCase):
    def test_preset_for_silverfox_and_kistie(self):
        class P:
            def __init__(self, slug):
                self.slug = slug

        self.assertEqual(preset_for_project(P("silverfox")), "silverfox")
        self.assertEqual(preset_for_project(P("kistie-store")), "kistie-store")
        self.assertEqual(preset_for_project(P("agripay-logistics-ai")), "agripay-logistics-ai")
        self.assertIsNone(preset_for_project(P("elite-fintech-systems")))

    def test_name_matches_ignores_spaces_and_case(self):
        self.assertTrue(_name_matches("SilverFox", "silverfox"))
        self.assertTrue(_name_matches("Kistie Store", "kistie-store"))
        self.assertFalse(_name_matches("Postgres", "SilverFox"))
