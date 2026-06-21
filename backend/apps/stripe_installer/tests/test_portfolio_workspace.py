from django.test import SimpleTestCase

from apps.stripe_installer.portfolio_workspace import (
    is_automation_center_clone_path,
    should_repair_local_path,
)


class PortfolioWorkspaceTests(SimpleTestCase):
    def test_detects_clone_path(self):
        path = r"C:\Software Projects\Deployment-Stripe-center\backend\clones\silverfox"
        self.assertTrue(is_automation_center_clone_path(path))

    def test_should_repair_silverfox_clone(self):
        class P:
            slug = "silverfox"
            local_path = r"C:\Software Projects\Deployment-Stripe-center\backend\clones\silverfox"

        self.assertTrue(should_repair_local_path(P()))
