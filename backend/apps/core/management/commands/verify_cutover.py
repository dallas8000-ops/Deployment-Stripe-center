"""Verify production cutover checklist against live endpoints."""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand


UNIFIED_HEALTH = "https://stripe-installer-production.up.railway.app/health/"
LEGACY_HEALTH = "https://api-transfer-production.up.railway.app/health/"
UNIFIED_WEBHOOK = "https://stripe-installer-production.up.railway.app/api/v1/billing/webhook/"
LEGACY_WEBHOOK = "https://api-transfer-production.up.railway.app/api/billing/webhook"


def _fetch_json(url: str, timeout: int = 15) -> tuple[int | None, dict | str]:
    req = urllib.request.Request(url, headers={"User-Agent": "deployment-stripe-center-cutover/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body[:200]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.reason
    except Exception as exc:
        return None, str(exc)


class Command(BaseCommand):
    help = "Check live cutover status (health endpoints, registry, remaining manual steps)"

    def handle(self, *args, **options):
        ok: list[str] = []
        warn: list[str] = []
        fail: list[str] = []

        status, unified = _fetch_json(UNIFIED_HEALTH)
        if status == 200 and isinstance(unified, dict) and unified.get("status") == "ok":
            ok.append(f"Unified health OK ({UNIFIED_HEALTH})")
            checks = unified.get("checks") or {}
            if checks.get("vault") == "ok":
                ok.append("Production vault check OK")
            else:
                warn.append(f"Unified vault check: {checks.get('vault', 'unknown')}")
        else:
            fail.append(f"Unified health failed ({status}): {unified}")

        status, legacy = _fetch_json(LEGACY_HEALTH)
        if status == 200:
            warn.append(
                "Legacy api-transfer-production still responds - delete Railway service after 48h quiet"
            )
        else:
            ok.append("Legacy api-transfer health unreachable (already down or removed)")

        from apps.stripe_installer.portfolio_paths import portfolio_registry_path

        reg_path = portfolio_registry_path()
        if reg_path.is_file():
            raw = json.loads(reg_path.read_text(encoding="utf-8"))
            apps = raw.get("allowedApps") or []
            ids = [a.get("id") for a in apps if isinstance(a, dict)]
            if "api-transfer-legacy" in ids:
                warn.append(f"{reg_path} still lists api-transfer-legacy - remove after cutover")
            elif "automation-center" in ids:
                ok.append(f"Portfolio registry OK ({reg_path})")
            else:
                warn.append(f"{reg_path} missing automation-center entry")
        else:
            warn.append(f"No portfolio registry at {reg_path} - run ensure_registry_template or copy example")

        legacy_webhook_disabled = False
        unified_webhook_enabled = False
        stripe_bin = shutil.which("stripe")
        if stripe_bin:
            try:
                proc = subprocess.run(
                    [stripe_bin, "webhook_endpoints", "list", "--live"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    payload = json.loads(proc.stdout)
                    for endpoint in payload.get("data") or []:
                        url = str(endpoint.get("url") or "")
                        status = str(endpoint.get("status") or "")
                        if url.rstrip("/") == LEGACY_WEBHOOK.rstrip("/"):
                            if status == "disabled":
                                legacy_webhook_disabled = True
                                ok.append(f"Legacy Stripe webhook disabled ({LEGACY_WEBHOOK})")
                            else:
                                warn.append(f"Legacy Stripe webhook still {status} ({LEGACY_WEBHOOK})")
                        if url.rstrip("/") == UNIFIED_WEBHOOK.rstrip("/"):
                            if status == "enabled":
                                unified_webhook_enabled = True
                                ok.append(f"Unified Stripe webhook enabled ({UNIFIED_WEBHOOK})")
                            else:
                                warn.append(f"Unified Stripe webhook status: {status}")
            except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError) as exc:
                warn.append(f"Could not check Stripe webhooks via CLI: {exc}")
        else:
            warn.append("Stripe CLI not found - install to auto-check webhook status")

        manual = [
            "Railway: merge API Transfer env vars onto stripe-installer-production (railway login required)",
            "Railway: delete api-transfer-production service after 48h no traffic",
            "Optional: archive local API Transfer folder",
        ]
        if not legacy_webhook_disabled:
            manual.insert(
                1,
                "Stripe: disable webhook at " + LEGACY_WEBHOOK
                + " (stripe webhook_endpoints update we_1ThOh0RxznXvj6jhjt7jZ3nm --disabled=true --live -c)",
            )
        if not unified_webhook_enabled:
            manual.insert(
                1 if legacy_webhook_disabled else 2,
                "Stripe: keep webhook enabled at " + UNIFIED_WEBHOOK,
            )

        for line in ok:
            self.stdout.write(self.style.SUCCESS(f"  OK   {line}"))
        for line in warn:
            self.stdout.write(self.style.WARNING(f"  WARN {line}"))
        for line in fail:
            self.stdout.write(self.style.ERROR(f"  FAIL {line}"))

        self.stdout.write("\nManual steps remaining:")
        for line in manual:
            self.stdout.write(f"  - {line}")

        if fail:
            raise SystemExit(1)
