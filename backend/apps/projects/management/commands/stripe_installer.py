"""Stripe Installer CLI — parity with legacy Node `stripe-installer` commands."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.projects.models import Project


class Command(BaseCommand):
    help = "Stripe Installer CLI (scan, verify, run, deploy, clone, vault-import, …)"

    def add_arguments(self, parser):
        parser.add_argument("--user", default="", help="Project owner email (default: first user)")
        subs = parser.add_subparsers(dest="command", required=True)

        scan = subs.add_parser("scan", help="Scan project local path")
        scan.add_argument("slug")
        scan.add_argument("--path", default="")

        verify = subs.add_parser("verify", help="Verify Stripe keys")
        verify.add_argument("slug")

        run = subs.add_parser("run", help="Run full setup pipeline")
        run.add_argument("slug")
        run.add_argument("--sync-env", action="store_true")
        run.add_argument("--force", action="store_true")

        deploy = subs.add_parser("deploy", help="Run deploy prep pipeline")
        deploy.add_argument("slug")
        deploy.add_argument("--push", action="store_true")
        deploy.add_argument("--force", action="store_true")

        clone = subs.add_parser("clone", help="Clone git_url into workspace")
        clone.add_argument("slug")
        clone.add_argument("--branch", default="")
        clone.add_argument("--force", action="store_true")

        pr = subs.add_parser("open-pr", help="Open GitHub PR with generated changes")
        pr.add_argument("slug")

        imp = subs.add_parser("vault-import", help="Import .env.local into vault")
        imp.add_argument("slug")
        imp.add_argument("--env-file", default=".env.local")

        diag = subs.add_parser("diagnose", help="Run diagnostics")
        diag.add_argument("slug")

        portfolio = subs.add_parser(
            "portfolio-audit",
            help="Audit all Stripe webhooks; write local report (~/.stripe-installer/reports/)",
        )
        portfolio.add_argument(
            "--project",
            default="",
            help="Project slug whose vault STRIPE_SECRET_KEY audits the whole Stripe account",
        )
        portfolio.add_argument("--user", default="", help="Owner email (default: first user)")
        portfolio.add_argument(
            "--fix",
            action="store_true",
            help="Re-register webhooks for registry apps (matched projects only)",
        )
        portfolio.add_argument("--dry-run", action="store_true", help="With --fix, show actions only")

        ready = subs.add_parser("readiness", help="Run readiness checks")
        ready.add_argument("slug")

    def handle(self, *args, **options):
        cmd = options["command"]
        if cmd == "portfolio-audit":
            self._portfolio_audit(options)
            return
        slug = options.get("slug")
        project = self._project(slug, options.get("user", ""))

        if cmd == "scan":
            self._scan(project, options.get("path") or project.local_path)
        elif cmd == "verify":
            self._verify(project)
        elif cmd == "run":
            self._run(project, options)
        elif cmd == "deploy":
            self._deploy(project, options)
        elif cmd == "clone":
            self._clone(project, options)
        elif cmd == "open-pr":
            self._open_pr(project)
        elif cmd == "vault-import":
            self._vault_import(project, options["env_file"])
        elif cmd == "diagnose":
            self._diagnose(project)
        elif cmd == "readiness":
            self._readiness(project)
        else:
            raise CommandError(f"Unknown command: {cmd}")

    def _user(self, email: str):
        User = get_user_model()
        if email:
            return User.objects.get(email=email)
        user = User.objects.first()
        if not user:
            raise CommandError("No users — register via UI or createsuperuser first")
        return user

    def _project(self, slug: str, email: str) -> Project:
        return Project.objects.get(slug=slug, owner=self._user(email))

    def _scan(self, project: Project, path: str) -> None:
        from pathlib import Path

        from apps.deploy.platform import detect_deploy_platform
        from apps.projects.scanner import ProjectScanner
        from apps.stripe_installer.portfolio_catalog import catalog_by_slug
        from apps.stripe_installer.portfolio_workspace import relative_scan_root, resolve_scan_root

        if not path:
            raise CommandError("Set --path or project local_path")
        repo_root = Path(path).resolve()
        scan_root = resolve_scan_root(repo_root)
        result = ProjectScanner(scan_root).scan()
        data = result.to_dict()
        catalog = catalog_by_slug(project.slug or "")
        production_url = str((catalog or {}).get("productionUrl") or "")
        backend_rel = relative_scan_root(repo_root, scan_root)
        if backend_rel:
            data["scanBackendPath"] = backend_rel
        data["deployPlatform"] = detect_deploy_platform(
            scan_root,
            data.get("framework", "unknown"),
            production_url=production_url,
        )
        if catalog:
            if catalog.get("productionUrl"):
                url = str(catalog["productionUrl"]).rstrip("/")
                data["productionUrl"] = url
                data["production_url"] = url
            if catalog.get("webhookPath"):
                data["webhookPath"] = catalog["webhookPath"]
        project.local_path = str(repo_root)
        project.framework = data["framework"]
        project.language = data["language"]
        project.scan_data = data
        project.save()
        self.stdout.write(self.style.SUCCESS(f"Scanned {path} — {data['framework']}"))

    def _verify(self, project: Project) -> None:
        from apps.stripe_installer.verify import verify_stripe_keys
        from apps.vault.models import get_secret

        result = verify_stripe_keys(
            get_secret(project, "STRIPE_SECRET_KEY"),
            get_secret(project, "STRIPE_PUBLISHABLE_KEY"),
        )
        self.stdout.write(str(result.to_public_dict()))

    def _run(self, project: Project, options: dict) -> None:
        from apps.stripe_installer.pipeline import PipelineOptions, run_pipeline

        result = run_pipeline(
            project,
            opts=PipelineOptions(sync_env=options["sync_env"], force=options["force"]),
        )
        self.stdout.write(self.style.SUCCESS(f"Done — readiness {result.readiness_score}"))

    def _deploy(self, project: Project, options: dict) -> None:
        from apps.deploy.pipeline import DeployOptions, run_deploy_pipeline

        result = run_deploy_pipeline(
            project,
            opts=DeployOptions(force=options["force"], push_platform=options["push"]),
        )
        for step in result.next_steps:
            self.stdout.write(f"→ {step}")

    def _clone(self, project: Project, options: dict) -> None:
        from apps.projects.git_clone import clone_project_repo

        out = clone_project_repo(
            project,
            branch=options.get("branch") or None,
            force=options["force"],
        )
        self.stdout.write(self.style.SUCCESS(f"{out['action']} → {out['local_path']}"))

    def _open_pr(self, project: Project) -> None:
        from apps.projects.github_pr import create_setup_pull_request

        out = create_setup_pull_request(project)
        self.stdout.write(self.style.SUCCESS(out["url"]))

    def _vault_import(self, project: Project, env_file: str) -> None:
        from pathlib import Path

        from apps.vault.import_env import import_env_to_vault

        if not project.local_path:
            raise CommandError("Set project local_path first")
        keys = import_env_to_vault(project, Path(project.local_path), env_file)
        self.stdout.write(self.style.SUCCESS(f"Imported: {', '.join(keys)}"))

    def _diagnose(self, project: Project) -> None:
        from pathlib import Path

        from apps.diagnostics.diagnostics import run_diagnostics

        if not project.local_path:
            raise CommandError("Set project local_path first")
        report = run_diagnostics(project, Path(project.local_path))
        self.stdout.write(f"Health: {report.health_score}/100 — {report.summary}")

    def _readiness(self, project: Project) -> None:
        from pathlib import Path

        from apps.stripe_installer.readiness import run_readiness_checks, score_readiness

        if not project.local_path:
            raise CommandError("Set project local_path first")
        checks = run_readiness_checks(project, Path(project.local_path))
        score = score_readiness(checks)
        self.stdout.write(f"Readiness: {score}/100")

    def _portfolio_audit(self, options: dict) -> None:
        import os

        from apps.stripe_installer.portfolio_audit import (
            fix_webhooks_for_projects,
            run_portfolio_audit,
            write_portfolio_report,
        )
        from apps.stripe_installer.portfolio_registry import ensure_registry_template, load_registry
        from apps.vault.models import get_secret

        ensure_registry_template()
        registry = load_registry()
        self.stdout.write(f"Registry: {ensure_registry_template()}")

        secret = os.environ.get("STRIPE_SECRET_KEY", "").strip()
        publishable = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip() or None
        project_slug = (options.get("project") or "").strip()

        owner = self._user(options.get("user", ""))
        projects = list(Project.objects.filter(owner=owner))

        if project_slug:
            project = Project.objects.get(slug=project_slug, owner=owner)
            secret = secret or (get_secret(project, "STRIPE_SECRET_KEY") or "")
            publishable = publishable or get_secret(project, "STRIPE_PUBLISHABLE_KEY")

        if not secret:
            raise CommandError(
                "Set STRIPE_SECRET_KEY in env or pass --project <slug> with keys in vault"
            )

        data = run_portfolio_audit(
            secret_key=secret,
            publishable_key=publishable,
            registry_apps=registry,
        )
        md_path, json_path = write_portfolio_report(data)
        self.stdout.write(self.style.SUCCESS(f"Report: {md_path}"))
        self.stdout.write(f"JSON: {json_path}")
        self.stdout.write(
            f"Endpoints: {data['summary']['endpointCount']} total, "
            f"{data['summary']['failingCount']} with issues"
        )

        if options.get("fix"):
            fixes = fix_webhooks_for_projects(
                projects,
                registry,
                dry_run=options.get("dry_run", False),
            )
            for row in fixes:
                if row.get("ok"):
                    self.stdout.write(self.style.SUCCESS(f"Fix {row['app']}: {row.get('webhookUrl', 'ok')}"))
                else:
                    self.stdout.write(self.style.ERROR(f"Fix {row['app']}: {row.get('message')}"))
