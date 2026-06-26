from django.test import SimpleTestCase
from unittest.mock import patch

from apps.stripe_core.portfolio_link_audit import run_portfolio_link_audit


class PortfolioLinkAuditTests(SimpleTestCase):
    @patch("apps.stripe_core.portfolio_link_audit._probe_url")
    def test_flags_http_500_as_failing(self, mock_probe):
        from apps.stripe_core.portfolio_audit import EndpointProbe

        mock_probe.return_value = EndpointProbe(
            url="https://example.com",
            reachable=False,
            status_code=500,
            message="HTTP 500",
            latency_ms=10.0,
        )
        data = run_portfolio_link_audit(timeout=1.0)
        self.assertGreater(data["summary"]["failing"], 0)
        self.assertTrue(any(not row["ok"] for row in data["links"]))

    @patch("apps.stripe_core.portfolio_link_audit._probe_url")
    def test_all_ok_when_probes_succeed(self, mock_probe):
        from apps.stripe_core.portfolio_audit import EndpointProbe

        mock_probe.return_value = EndpointProbe(
            url="https://example.com",
            reachable=True,
            status_code=200,
            message="HTTP 200",
            latency_ms=5.0,
        )
        data = run_portfolio_link_audit(timeout=1.0)
        self.assertEqual(data["summary"]["failing"], 0)
