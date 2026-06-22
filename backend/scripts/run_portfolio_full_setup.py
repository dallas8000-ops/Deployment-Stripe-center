#!/usr/bin/env python
"""Run full setup (deploy pipeline) + hub bootstrap for entire portfolio."""
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
from apps.deploy.pipeline import DeployOptions, run_deploy_pipeline
from apps.deploy.platform_bootstrap import bootstrap_platform_automation
from apps.projects.models import Project
from apps.stripe_installer.hub_keys import HUB_SLUG
from apps.stripe_installer.portfolio_catalog import is_stripe_exempt_slug, stripe_billing_apps

EMAIL = "dallas8000@gmail.com"


def run_full_setup(project: Project) -> dict:
    exempt = is_stripe_exempt_slug(project.slug)
    try:
        result = run_deploy_pipeline(
            project,
            opts=DeployOptions(
                provision_stripe=not exempt and project.slug != HUB_SLUG,
                generate_code=True,
                include_infra=True,
                provision_postgres=not exempt,
                include_readiness=True,
                push_railway_env=True,
                force=False,
            ),
        )
        return {
            "ok": True,
            "readiness": result.pipeline.readiness_score,
            "platform": result.platform,
            "env_push": bool(result.env_push_result),
            "next_steps": result.next_steps[:3],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def main() -> int:
    user = get_user_model().objects.get(email=EMAIL)
    hub = Project.objects.get(slug=HUB_SLUG, owner=user)

    print("\n=== 1) Hub bootstrap (vault sync, master key pin, env push all) ===\n")
    boot = bootstrap_platform_automation(hub, user=user)
    print("bootstrap ok:", boot.get("ok"), "-", boot.get("message"))
    for action in boot.get("actions", []):
        name = action.get("action", "?")
        ok = action.get("ok", action.get("action") != "pin_master_key_railway" or "ok" in action)
        if name == "pin_master_key_railway":
            print(f"  pin VAULT_MASTER_KEY: {'OK' if action.get('ok') else 'FAIL'} {action.get('detail', action.get('message', ''))[:120]}")
        elif name == "reconcile_master_key":
            print(f"  master key: {action.get('action', action.get('message', 'OK'))}")
        else:
            print(f"  {name}: {action}")

    for row in boot.get("projects", []):
        mark = "OK" if row.get("ok") else "FAIL"
        print(f"  [{mark}] {row['slug']}")

    slugs = [HUB_SLUG] + [e["projectSlug"] for e in stripe_billing_apps() if e["projectSlug"] != HUB_SLUG]
    exempt = ["blog-2", "kistie-store", "silverfox"]
    for s in exempt:
        if Project.objects.filter(slug=s, owner=user).exists() and s not in slugs:
            slugs.append(s)

    print("\n=== 2) Full setup (deploy pipeline) per app ===\n")
    results: list[tuple[str, dict]] = []
    for slug in slugs:
        project = Project.objects.get(slug=slug, owner=user)
        print(f"Running {slug}...", flush=True)
        out = run_full_setup(project)
        results.append((slug, out))
        if out.get("ok"):
            print(f"  OK readiness={out.get('readiness')} env_push={out.get('env_push')}")
        else:
            print(f"  FAIL {out.get('error')}")

    # Fix retired api-transfer path
    print("\n=== 3) Cleanup retired api-transfer ===\n")
    retired = Project.objects.filter(slug="api-transfer", owner=user).first()
    if retired:
        retired.local_path = str(Path(hub.local_path).resolve())
        retired.save(update_fields=["local_path", "updated_at"])
        print("api-transfer local_path -> hub (retired project)")

    failed = [s for s, r in results if not r.get("ok")]
    print(f"\n{'=' * 44}")
    print(f"Full setup: {len(results) - len(failed)}/{len(results)} succeeded")
    if failed:
        print("Failures:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
