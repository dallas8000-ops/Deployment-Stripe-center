import type { DeployConfig, DeployPlatform, ProjectProfile } from "../types.js";
import { postgresSchema, postgresClientLib, postgresWebhookSync, postgresSetupGuide } from "./postgres.js";
import { platformDeployCommand } from "./platform-detector.js";
import {
  frameworkBuildCommand,
  frameworkStartCommand,
  generateDockerfile,
  generateHealthRoute,
  getDeployPaths,
  healthCheckPath,
  productionEnvKeys,
} from "./framework-deploy.js";
import { libDir } from "../stripe/framework-profiles.js";
import { stripeDbImportPath } from "../stripe/session-routes.js";

export class InfraCodeGenerator {
  constructor(
    private readonly profile: ProjectProfile,
    private readonly config: DeployConfig,
    private readonly platform: DeployPlatform
  ) {}

  generateAll(): Record<string, string> {
    const files: Record<string, string> = {};
    const prodUrl = this.config.productionUrl ?? `https://${this.config.domain ?? "your-domain.com"}`;
    const paths = getDeployPaths(this.profile, prodUrl);
    const lib = libDir(this.profile);
    const dbImportForStripeDb = stripeDbImportPath(this.profile);

    files["db/schema.sql"] = postgresSchema();
    if (this.profile.language === "typescript" || this.profile.language === "javascript") {
      files[`${lib}/db.ts`] = postgresClientLib();
      files[`${lib}/stripe-db.ts`] = postgresWebhookSync(dbImportForStripeDb);
    }
    files["deploy/POSTGRES-SETUP.md"] = postgresSetupGuide(this.config.postgres?.provider ?? "neon");
    files["deploy/DNS-SSL-SETUP.md"] = this.dnsSslGuide(prodUrl, paths.webhookUrl, paths.healthUrl);
    files["deploy/DEPLOY.md"] = this.deployGuide(prodUrl, paths.healthUrl);
    files["scripts/backup-db.sh"] = this.backupScriptSh();
    files["scripts/backup-db.ps1"] = this.backupScriptPs1();
    files["Dockerfile"] = generateDockerfile(this.profile);

    Object.assign(files, generateHealthRoute(this.profile, paths.dbImport));

    if (this.platform === "vercel" && this.profile.framework === "nextjs") {
      files["vercel.json"] = this.vercelConfig(prodUrl, paths.webhookPath);
    } else if (this.platform === "railway") {
      files["railway.toml"] = this.railwayConfig(paths.healthUrl);
    }

    if (this.config.monitoring?.sentry) {
      files["sentry.client.config.ts"] = this.sentryConfig();
    }

    files[".env.production.example"] = productionEnvKeys(this.profile, prodUrl);
    return files;
  }

  private vercelConfig(prodUrl: string, webhookPath: string): string {
    return JSON.stringify({
      "$schema": "https://openapi.vercel.sh/vercel.json",
      framework: "nextjs",
      regions: ["iad1"],
      headers: [
        {
          source: webhookPath,
          headers: [{ key: "Cache-Control", value: "no-store" }],
        },
      ],
      env: {
        NEXT_PUBLIC_APP_URL: prodUrl,
      },
      _comment: "SSL is automatic on Vercel. Add custom domain in Project Settings → Domains.",
    }, null, 2);
  }

  private railwayConfig(healthUrl: string): string {
    const healthPath = healthUrl.replace(/^https?:\/\/[^/]+/, "") || healthCheckPath(this.profile.framework);
    return `[build]
builder = "nixpacks"
buildCommand = "${frameworkBuildCommand(this.profile)}"

[deploy]
startCommand = "${frameworkStartCommand(this.profile)}"
healthcheckPath = "${healthPath}"
healthcheckTimeout = 30
restartPolicyType = "on_failure"

# Add PostgreSQL plugin in Railway dashboard
# SSL is automatic on Railway
`;
  }

  private sentryConfig(): string {
    return `// Optional Sentry monitoring — npm install @sentry/nextjs
// Run: npx @sentry/wizard@latest -i nextjs
export const sentryConfig = {
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: 0.1,
  environment: process.env.NODE_ENV,
};
`;
  }

  private backupScriptSh(): string {
    const retention = this.config.backup?.retentionDays ?? 7;
    return `#!/usr/bin/env bash
# Database backup — run via cron: 0 2 * * * ./scripts/backup-db.sh
set -euo pipefail

if [ -z "\${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL not set"
  exit 1
fi

BACKUP_DIR="\${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/backup-$(date +%Y%m%d-%H%M%S).sql"

pg_dump "$DATABASE_URL" > "$FILE"
gzip "$FILE"
echo "Backup: $FILE.gz"

# Prune old backups
find "$BACKUP_DIR" -name "backup-*.sql.gz" -mtime +${retention} -delete
`;
  }

  private backupScriptPs1(): string {
    const retention = this.config.backup?.retentionDays ?? 7;
    return `# Database backup script (Windows)
# Schedule via Task Scheduler: daily at 2 AM
param([string]$BackupDir = ".\\backups")

if (-not $env:DATABASE_URL) { Write-Error "DATABASE_URL not set"; exit 1 }
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$file = Join-Path $BackupDir "backup-$timestamp.sql"

# Requires pg_dump in PATH (PostgreSQL client tools)
pg_dump $env:DATABASE_URL -f $file
Write-Host "Backup: $file"

# Prune backups older than ${retention} days
Get-ChildItem $BackupDir -Filter "backup-*.sql" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-${retention}) } |
  Remove-Item -Force
`;
  }

  private dnsSslGuide(prodUrl: string, webhookUrl: string, healthUrl: string): string {
    const domain = this.config.domain ?? new URL(prodUrl).hostname;
    return `# Domain & SSL Setup

Production URL: ${prodUrl}
Domain: ${domain}
Framework: ${this.profile.framework}

## SSL
SSL/TLS is **automatic** on these platforms (no manual cert setup):
- **Vercel** — Let's Encrypt, auto-renewed
- **Railway** — HTTPS on *.up.railway.app and custom domains
- **Fly.io** — fly certs add ${domain}

## DNS Records (custom domain)

### Vercel
| Type  | Name | Value                |
|-------|------|----------------------|
| A     | @    | 76.76.21.21          |
| CNAME | www  | cname.vercel-dns.com |

### Railway
Follow dashboard instructions — typically CNAME to platform hostname.

## Stripe Webhook (production)
Update webhook URL to: \`${webhookUrl}\`
\`\`\`bash
stripe-installer automate --provision --config stripe.config.json
\`\`\`
Set productionUrl in deploy.config.json first.

## Verification
\`\`\`bash
stripe-installer readiness
curl ${healthUrl}
\`\`\`
`;
  }

  private deployGuide(prodUrl: string, healthUrl: string): string {
    const cmd = platformDeployCommand(this.platform);
    const envBlock = productionEnvKeys(this.profile, prodUrl);
    return `# Deployment Guide

Platform: **${this.platform}**
Framework: **${this.profile.framework}**
Production URL: ${prodUrl}

## Pre-deploy checklist
1. Run \`stripe-installer readiness\` — aim for 80+ score
2. Switch to **live** Stripe keys in vault
3. Set DATABASE_URL for production PostgreSQL
4. Apply schema: \`psql $DATABASE_URL -f db/schema.sql\`

## Environment variables (set in platform dashboard)
\`\`\`
${envBlock}\`\`\`

## Deploy
\`\`\`bash
${cmd}
# Or: docker build -t app . && docker run -p 3000:3000 --env-file .env.production app
\`\`\`

## Post-deploy
1. Verify SSL: ${prodUrl}
2. Test health: ${healthUrl}
3. Register production Stripe webhook
4. Test checkout with real card (small amount)
5. Schedule backups: scripts/backup-db.sh
`;
  }
}
