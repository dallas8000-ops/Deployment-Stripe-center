"""Run Setup Hub automation for all billing portfolio apps."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import stripe  # noqa: E402

from apps.projects.models import Project  # noqa: E402
from apps.stripe_core.portfolio_catalog import is_stripe_exempt_slug  # noqa: E402
from apps.stripe_core.setup_hub import (  # noqa: E402
    register_webhooks_for_user,
    reset_workspace,
    sync_registry_for_user,
)
from apps.vault.models import get_secret  # noqa: E402


def _key_status(val: str) -> str:
    if not val:
        return "MISSING"
    if val.startswith("sk_"):
        return "sk_ok"
    if val.startswith("whsec_"):
        return "whsec_ok"
    return "BAD_PREFIX"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run Setup Hub for all billing apps")
    parser.add_argument("--user", default="dallas8000@gmail.com", help="Owner email")
    args = parser.parse_args()

    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        owner = User.objects.get(email=args.user.strip())
    except User.DoesNotExist:
        print(f"ERROR: no user {args.user}")
        return 1

    hub = Project.objects.filter(owner=owner, slug="stripe-installer").first()
    if not hub:
        print(f"ERROR: stripe-installer project not found for {args.user}")
        return 1
    secret = get_secret(hub, "STRIPE_SECRET_KEY")
    if not secret:
        print("ERROR: STRIPE_SECRET_KEY missing from hub vault")
        return 1

    stripe.api_key = secret

    print("=== 1. Sync portfolio registry ===")
    print(sync_registry_for_user(owner))

    print("\n=== 2. Reset workspaces ===")
    print("hub:", reset_workspace(hub).get("registryPath"))
    for project in Project.objects.filter(owner=owner).order_by("slug"):
        if project.slug == "stripe-installer" or is_stripe_exempt_slug(project.slug):
            continue
        reset_workspace(project)
        print(f"  reset: {project.slug}")

    print("\n=== 3. Vault key format (before webhook register) ===")
    for project in Project.objects.filter(owner=owner).order_by("slug"):
        if is_stripe_exempt_slug(project.slug):
            print(f"  {project.slug}: EXEMPT")
            continue
        sk = get_secret(project, "STRIPE_SECRET_KEY") or ""
        wh = get_secret(project, "STRIPE_WEBHOOK_SECRET") or ""
        issues = []
        if _key_status(sk) != "sk_ok":
            issues.append(f"STRIPE_SECRET_KEY={_key_status(sk)}")
        if _key_status(wh) != "whsec_ok":
            issues.append(f"STRIPE_WEBHOOK_SECRET={_key_status(wh)}")
        print(f"  {project.slug}:", "OK" if not issues else ", ".join(issues))

    print("\n=== 4. Register webhooks + push Railway env ===")
    results = register_webhooks_for_user(owner)
    from apps.deploy.env_push import try_auto_push_railway_stripe_env

    for row in results:
        app = row.get("app", "?")
        ok = row.get("ok")
        stored = row.get("webhookSecretStored")
        detail = row.get("message") or row.get("webhookUrl") or ""
        slug = None
        for p in Project.objects.filter(owner=owner):
            from apps.stripe_core.hub_keys import portfolio_app_for_project

            pa = portfolio_app_for_project(p)
            if pa and pa.id == app:
                slug = p.slug
                break
        env_ok = None
        if slug and not is_stripe_exempt_slug(slug):
            project = Project.objects.get(slug=slug, owner=owner)
            env = try_auto_push_railway_stripe_env(project) or {}
            env_ok = env.get("ok")
            row["envPush"] = env
        print(f"  {app}: ok={ok} secret_stored={stored} railway_push={env_ok} {detail}")

    print("\n=== 5. Platform bootstrap (vault sync; skips missing folders) ===")
    from apps.stripe_core.hub_keys import sync_vault_to_billing_projects, sync_deploy_keys_to_portfolio_projects

    sync_vault_to_billing_projects(hub, owner)
    sync_deploy_keys_to_portfolio_projects(hub, owner)
    boot = {"ok": True, "projects": []}
    for project in Project.objects.filter(owner=owner).order_by("slug"):
        if project.slug == "stripe-installer" or is_stripe_exempt_slug(project.slug):
            continue
        if not (project.local_path or "").strip():
            boot["projects"].append({"slug": project.slug, "ok": False, "message": "local_path missing"})
            continue
        from pathlib import Path

        if not Path(project.local_path).is_dir():
            boot["projects"].append({"slug": project.slug, "ok": False, "message": "folder not found"})
            continue
        env = try_auto_push_railway_stripe_env(project) or {}
        boot["projects"].append(
            {"slug": project.slug, "ok": bool(env.get("ok")), "message": env.get("message", "")}
        )
    print("bootstrap ok:", boot.get("ok"))
    for project_row in boot.get("projects") or []:
        slug = project_row.get("slug", "?")
        ok = project_row.get("ok")
        msg = (project_row.get("message") or "")[:100]
        print(f"  {slug}: ok={ok} {msg}")

    print("\n=== 6. Vault key format (after setup) ===")
    bad = 0
    for project in Project.objects.filter(owner=owner).order_by("slug"):
        if is_stripe_exempt_slug(project.slug):
            continue
        sk = get_secret(project, "STRIPE_SECRET_KEY") or ""
        wh = get_secret(project, "STRIPE_WEBHOOK_SECRET") or ""
        issues = []
        if _key_status(sk) != "sk_ok":
            issues.append(f"STRIPE_SECRET_KEY={_key_status(sk)}")
        if _key_status(wh) != "whsec_ok":
            issues.append(f"STRIPE_WEBHOOK_SECRET={_key_status(wh)}")
        if issues:
            bad += 1
            print(f"  {project.slug}: FAIL — {', '.join(issues)}")
        else:
            print(f"  {project.slug}: OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
