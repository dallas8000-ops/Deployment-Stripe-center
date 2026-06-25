from django.test import SimpleTestCase

from apps.stripe_core.portfolio_workspace import (
    is_automation_center_nested_path,
    is_inside_hub_repo,
    is_invalid_portfolio_path,
    repair_portfolio_local_path,
    resolve_workspace_path,
    should_repair_local_path,
    workspace_path_error,
)


class PortfolioWorkspaceTests(SimpleTestCase):
    def test_detects_nested_hub_path(self):
        path = r"C:\Software Projects\Deployment-Stripe-center\backend\clones\silverfox"
        self.assertTrue(is_automation_center_nested_path(path))
        self.assertTrue(is_inside_hub_repo(path))

    def test_should_repair_silverfox_inside_hub(self):
        class P:
            slug = "silverfox"
            local_path = r"C:\Software Projects\Deployment-Stripe-center\backend\clones\silverfox"
            git_url = ""

        self.assertTrue(should_repair_local_path(P()))

    def test_resolve_workspace_prefers_catalog_over_hub(self):
        class P:
            slug = "silverfox"
            local_path = r"C:\Software Projects\Deployment-Stripe-center\backend\clones\silverfox"
            git_url = ""

        target = resolve_workspace_path(P())
        self.assertEqual(target, r"C:\Software Projects\SilverFox")

    def test_workspace_path_error_rejects_hub_nested(self):
        class P:
            slug = "custom-app"
            local_path = r"C:\Software Projects\Deployment-Stripe-center\backend\clone6"
            git_url = ""

        self.assertTrue(is_invalid_portfolio_path(P(), P.local_path))
        err = workspace_path_error(P()) or ""
        self.assertTrue("cannot be inside" in err or "backend/clones" in err)

    def test_hub_project_allows_repo_root(self):
        class P:
            slug = "stripe-installer"
            local_path = r"C:\Software Projects\Deployment-Stripe-center"
            git_url = ""

        self.assertFalse(is_invalid_portfolio_path(P(), P.local_path))

    def test_repair_points_agripay_at_default_local_path(self):
        class P:
            slug = "agripay-logistics-ai"
            local_path = r"C:\Software Projects\Deployment-Stripe-center\backend\clones\agripay-logistics-ai"
            git_url = "https://github.com/example/agripay.git"

            def save(self, update_fields=None):
                pass

        p = P()
        path, changed = repair_portfolio_local_path(p, save=False)
        self.assertTrue(changed)
        self.assertEqual(path, r"C:\Software Projects\AgriPay Logistics AI")

    def test_repair_clears_invalid_hub_path_without_known_target(self):
        class P:
            slug = "custom-unknown-app"
            local_path = r"C:\Software Projects\Deployment-Stripe-center\backend\clones\custom-unknown-app"
            git_url = ""

            def save(self, update_fields=None):
                pass

        p = P()
        path, changed = repair_portfolio_local_path(p, save=False)
        self.assertTrue(changed)
        self.assertEqual(path, "")
