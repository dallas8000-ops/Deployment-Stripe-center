"""Compliance management command tests."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class ComplianceCheckTests(TestCase):
    def test_compliance_check_passes_with_empty_chain(self):
        out = StringIO()
        call_command("compliance_check", stdout=out)
        self.assertIn("chain valid", out.getvalue().lower())

    def test_verify_audit_chain_after_entry(self):
        from apps.api_transfer.audit import record_audit, verify_chain

        record_audit("discover", "test@example.com", {"ok": True})
        out = StringIO()
        call_command("verify_audit_chain", stdout=out)
        self.assertIn("valid", out.getvalue().lower())
        self.assertTrue(verify_chain()["valid"])
