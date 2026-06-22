#!/usr/bin/env python
"""Portfolio automation burn audit — complements live_burn_test.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from apps.deploy.preflight import run_deploy_preflight
from apps.projects.models import Project
from apps.stripe_installer.hub_keys import HUB_SLUG
from apps.stripe_installer.portfolio_catalog import DASHBOARD_HIDDEN_PROJECT_SLUGS, stripe_billing_apps
from apps.stripe_installer.setup_hub import setup_hub_status
from apps.vault.models import get_secret

EMAIL = "dallas8000@gmail.com"


def main() -> int:
    user = get_user_model().objects.get(email=EMAIL)
    hub = Project.objects.get(slug=HUB_SLUG, owner=user)
    issues: list[str] = []

    print("\n=== Automation audit ===\n")
    st = setup_hub_status(hub, user=user)
    print("HUB SETUP HUB")
    for s in st["steps"]:
        mark = "OK" if s["ok"] else "GAP"
        print(f"  [{mark}] {s['label']}")
        if not s["ok"]:
            issues.append(f"hub: {s['label']}")
    for s in st.get("platformAutomation", {}).get("steps", []):
        mark = "OK" if s["ok"] else "GAP"
        print(f"  [{mark}] {s['label']}")
        if not s["ok"]:
            issues.append(f"hub platform: {s['label']}")
    gaps = st.get("lastPortfolioAuditRegistryGaps") or []
    print(f"  webhook registry gaps: {len(gaps)}")
    if gaps:
        issues.append(f"webhook gaps: {len(gaps)}")
    print(f"  readyForPipeline: {st.get('readyForPipeline')}")

    billing = [e["projectSlug"] for e in stripe_billing_apps()]
    print("\nBILLING APPS")
    for slug in billing:
        p = Project.objects.get(slug=slug, owner=user)
        lp = p.local_path or ""
        clone = "clones" in lp.lower()
        path_ok = Path(lp).is_dir() if lp else False
        pf = run_deploy_preflight(p, push_railway_env=True, provision_postgres=False)
        pid = get_secret(p, "RAILWAY_PROJECT_ID") or ""
        sid = get_secret(p, "RAILWAY_SERVICE_ID") or ""
        pushed = (p.scan_data or {}).get("railway", {}).get("lastEnvPushAt") or "never"
        ok = pf["ok"] and path_ok and not clone and pid and sid
        mark = "OK" if ok else "GAP"
        print(f"  [{mark}] {slug:22} path={path_ok} clone={clone} ids={bool(pid and sid)} push={pushed}")
        if not path_ok:
            issues.append(f"{slug}: workspace missing")
        if clone:
            issues.append(f"{slug}: still on clone path")
        if not pf["ok"]:
            issues.extend(f"{slug}: {i}" for i in pf.get("issues") or [])
        if pushed == "never":
            issues.append(f"{slug}: env never pushed")

    print("\nEXEMPT (hidden)")
    for slug in sorted(DASHBOARD_HIDDEN_PROJECT_SLUGS):
        try:
            p = Project.objects.get(slug=slug, owner=user)
        except Project.DoesNotExist:
            continue
        lp = p.local_path or ""
        path_ok = Path(lp).is_dir() if lp else False
        clone = "clones" in lp.lower()
        mark = "OK" if path_ok and not clone else "GAP"
        print(f"  [{mark}] {slug:22} path={path_ok} clone={clone}")

    print(f"\n{'=' * 44}")
    if issues:
        print(f"Gaps remaining: {len(issues)}")
        for item in issues:
            print(f"  • {item}")
        return 1
    print("No automation gaps detected.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
