"""Infra file generation — port of legacy deploy/infra-generator.ts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from apps.projects.models import Project
from apps.stripe_engine.codegen.writer import WriteResult, write_project_files

from .platform import (
    detect_deploy_platform,
    framework_build_command,
    framework_start_command,
    health_check_path,
    platform_deploy_command,
    production_env_example,
    webhook_path_for,
)
from .postgres import schema_sql


def _prod_url(project: Project, fallback: str) -> str:
    scan = project.scan_data or {}
    url = scan.get("productionUrl") or scan.get("production_url") or fallback
    return str(url).rstrip("/") if url else fallback.rstrip("/")


def _postgres_provider(project: Project) -> str:
    scan = project.scan_data or {}
    postgres = scan.get("postgres") or {}
    return str(postgres.get("provider") or "neon")


def _backup_script_sh(retention: int = 7) -> str:
    return f"""#!/usr/bin/env bash
# Database backup — run via cron: 0 2 * * * ./scripts/backup-db.sh
set -euo pipefail

if [ -z "${{DATABASE_URL:-}}" ]; then
  echo "DATABASE_URL not set"
  exit 1
fi

BACKUP_DIR="${{BACKUP_DIR:-./backups}}"
mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/backup-$(date +%Y%m%d-%H%M%S).sql"

pg_dump "$DATABASE_URL" > "$FILE"
gzip "$FILE"
echo "Backup: $FILE.gz"

find "$BACKUP_DIR" -name "backup-*.sql.gz" -mtime +{retention} -delete
"""


def _backup_script_ps1(retention: int = 7) -> str:
    return f"""# Database backup script (Windows)
param([string]$BackupDir = ".\\backups")

if (-not $env:DATABASE_URL) {{ Write-Error "DATABASE_URL not set"; exit 1 }}
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$file = Join-Path $BackupDir "backup-$timestamp.sql"

pg_dump $env:DATABASE_URL -f $file
Write-Host "Backup: $file"

Get-ChildItem $BackupDir -Filter "backup-*.sql" |
  Where-Object {{ $_.LastWriteTime -lt (Get-Date).AddDays(-{retention}) }} |
  Remove-Item -Force
"""


def _postgres_setup_guide(provider: str) -> str:
    guides = {
        "neon": """# Neon PostgreSQL Setup
1. Create project at https://neon.tech
2. Copy pooled connection string
3. Store DATABASE_URL in Stripe Installer vault
4. Apply schema via Database panel or: psql $DATABASE_URL -f db/schema.sql
""",
        "supabase": """# Supabase PostgreSQL Setup
1. Create project at https://supabase.com
2. Settings → Database → Connection string (URI)
3. Store DATABASE_URL in vault
4. Apply schema via SQL Editor or Database panel
""",
    }
    return guides.get(provider, guides["neon"])


def _dns_ssl_guide(prod_url: str, webhook_url: str, health_url: str, framework: str) -> str:
    domain = urlparse(prod_url).hostname or "your-domain.com"
    return f"""# Domain & SSL Setup

Production URL: {prod_url}
Domain: {domain}
Framework: {framework}

## SSL
SSL/TLS is automatic on Vercel, Railway, Render, and Fly.io custom domains.

## Stripe Webhook (production)
Update webhook URL to: `{webhook_url}`

## Verification
```bash
curl {health_url}
```
Run readiness from Stripe Installer after deploy.
"""


def _deploy_guide(project: Project, platform: str, prod_url: str, health_url: str) -> str:
    cmd = platform_deploy_command(platform)
    env_block = production_env_example(project.framework, prod_url)
    return f"""# Deployment Guide

Platform: **{platform}**
Framework: **{project.framework}**
Production URL: {prod_url}

## Pre-deploy checklist
1. Run readiness — aim for 80+ score
2. Switch to **live** Stripe keys in vault
3. Set DATABASE_URL and apply schema
4. Set production URL in project settings

## Environment variables
```
{env_block}```

## Deploy
```bash
{cmd}
```

## Post-deploy
1. Verify SSL: {prod_url}
2. Test health: {health_url}
3. Register production Stripe webhook
4. Schedule backups: scripts/backup-db.sh
"""


def _health_route_next_app() -> str:
    return '''import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const checks: Record<string, string> = { app: "ok" };
  const payload = {
    status: "healthy",
    checks,
    timestamp: new Date().toISOString(),
  };
  return NextResponse.json(payload);
}
'''


def _health_route_django() -> str:
    return '''from datetime import datetime, timezone

from django.http import JsonResponse


def health(_request):
    return JsonResponse(
        {
            "status": "healthy",
            "checks": {"app": "ok"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        status=200,
    )
'''


def _health_route_express() -> str:
    return '''import { Router } from "express";

const router = Router();

router.get("/", async (_req, res) => {
  res.json({
    status: "healthy",
    checks: { app: "ok" },
    timestamp: new Date().toISOString(),
  });
});

export default router;
'''


def _platform_configs(platform: str, project: Project, prod_url: str, health_path: str, webhook_path: str) -> dict[str, str]:
    files: dict[str, str] = {}
    if platform == "vercel" and project.framework == "nextjs":
        files["vercel.json"] = json.dumps(
            {
                "$schema": "https://openapi.vercel.sh/vercel.json",
                "framework": "nextjs",
                "regions": ["iad1"],
                "headers": [
                    {
                        "source": webhook_path,
                        "headers": [{"key": "Cache-Control", "value": "no-store"}],
                    }
                ],
                "env": {"NEXT_PUBLIC_APP_URL": prod_url},
            },
            indent=2,
        )
    elif platform == "railway":
        files["railway.toml"] = f"""[build]
builder = "nixpacks"
buildCommand = "{framework_build_command(project.framework)}"

[deploy]
startCommand = "{framework_start_command(project.framework)}"
healthcheckPath = "{health_path}"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
"""
    elif platform == "render":
        app_key = "NEXT_PUBLIC_APP_URL" if project.framework == "nextjs" else "APP_URL"
        runtime = "python" if project.framework in ("django", "flask") else "node"
        files["render.yaml"] = f"""services:
  - type: web
    name: {project.slug}
    runtime: {runtime}
    buildCommand: {framework_build_command(project.framework)}
    startCommand: {framework_start_command(project.framework)}
    healthCheckPath: {health_path}
    envVars:
      - key: NODE_ENV
        value: production
      - key: {app_key}
        value: {prod_url}
"""
    return files


def generate_infra_files(project: Project, project_root: Path, *, prod_url: str) -> dict[str, str]:
    scan = project.scan_data or {}
    next_router = scan.get("nextRouter") or scan.get("next_router")
    platform = scan.get("deployPlatform") or detect_deploy_platform(project_root, project.framework)
    health_path = health_check_path(project.framework)
    webhook_path = webhook_path_for(project.framework, next_router)
    health_url = f"{prod_url}{health_path}"
    webhook_url = f"{prod_url}{webhook_path}"

    files: dict[str, str] = {
        "db/schema.sql": schema_sql(),
        "deploy/POSTGRES-SETUP.md": _postgres_setup_guide(_postgres_provider(project)),
        "deploy/DNS-SSL-SETUP.md": _dns_ssl_guide(prod_url, webhook_url, health_url, project.framework),
        "deploy/DEPLOY.md": _deploy_guide(project, platform, prod_url, health_url),
        "scripts/backup-db.sh": _backup_script_sh(),
        "scripts/backup-db.ps1": _backup_script_ps1(),
        ".env.production.example": production_env_example(project.framework, prod_url),
    }

    from .platform import generate_dockerfile

    files["Dockerfile"] = generate_dockerfile(project.framework)

    if project.framework == "nextjs" and next_router != "pages":
        files["app/api/health/route.ts"] = _health_route_next_app()
    elif project.framework == "django":
        files["stripe/health_views.py"] = _health_route_django()
    elif project.framework in ("express", "fastify"):
        files["src/routes/health.ts"] = _health_route_express()

    files.update(_platform_configs(platform, project, prod_url, health_path, webhook_path))
    return files


def generate_and_write_infra(
    project: Project,
    *,
    force: bool = False,
    prod_url: str | None = None,
) -> tuple[dict[str, str], list[WriteResult]]:
    if not project.local_path:
        raise ValueError("Set project local_path first.")
    root = Path(project.local_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project path not found: {root}")

    url = prod_url or _prod_url(project, "https://your-domain.com")
    files = generate_infra_files(project, root, prod_url=url)
    results = write_project_files(root, files, force=force)

    scan = dict(project.scan_data or {})
    scan["deployPlatform"] = scan.get("deployPlatform") or detect_deploy_platform(root, project.framework)
    scan["infraGeneratedAt"] = datetime.now(timezone.utc).isoformat()
    project.scan_data = scan
    project.save(update_fields=["scan_data", "updated_at"])

    return files, results


def infra_summary(files: dict[str, str]) -> dict[str, Any]:
    return {
        "fileCount": len(files),
        "paths": sorted(files.keys()),
    }
