import { readFile, access } from "node:fs/promises";
import { join } from "node:path";
import type { DeployConfig, ProjectProfile, ReadinessCheck } from "../types.js";
import type { SecretVault } from "../security/vault.js";
import { verifyApiKeys } from "../stripe/stripe-client.js";
import { StripeApiAutomation } from "../stripe/api-automation.js";
import { detectDeployPlatform } from "./platform-detector.js";
import { getDatabaseUrl, testPostgresConnection, validateDatabaseUrl } from "./postgres.js";

export async function runReadinessChecks(
  profile: ProjectProfile,
  vault: SecretVault,
  config: DeployConfig
): Promise<ReadinessCheck[]> {
  const checks: ReadinessCheck[] = [];
  const root = profile.rootPath;

  // Stripe checks
  const keys = await verifyApiKeys(vault);
  checks.push({
    id: "stripe-secret",
    category: "stripe",
    name: "Stripe secret key",
    status: keys.secretKey.valid ? "pass" : "fail",
    message: keys.secretKey.message,
    fix: "stripe-installer vault set STRIPE_SECRET_KEY sk_live_...",
  });

  checks.push({
    id: "stripe-live-mode",
    category: "stripe",
    name: "Production Stripe keys",
    status: keys.secretKey.mode === "live" ? "pass" : "warn",
    message: keys.secretKey.mode === "live" ? "Using live mode keys" : `Using ${keys.secretKey.mode} mode — switch to live for production`,
    fix: "Replace sk_test_ with sk_live_ keys in vault",
  });

  checks.push({
    id: "stripe-publishable",
    category: "stripe",
    name: "Stripe publishable key",
    status: keys.publishableKey.valid ? "pass" : "warn",
    message: keys.publishableKey.message,
    fix: "stripe-installer vault set STRIPE_PUBLISHABLE_KEY pk_live_...",
  });

  const webhookSecret = await vault.get("STRIPE_WEBHOOK_SECRET");
  checks.push({
    id: "stripe-webhook-secret",
    category: "stripe",
    name: "Webhook signing secret",
    status: webhookSecret ? "pass" : "warn",
    message: webhookSecret ? "Configured" : "STRIPE_WEBHOOK_SECRET missing",
    fix: "Run automate --provision with production webhook URL",
  });

  const automation = new StripeApiAutomation(root, vault);
  const manifest = await automation.loadManifest();
  checks.push({
    id: "stripe-manifest",
    category: "stripe",
    name: "Stripe catalog manifest",
    status: manifest && manifest.prices.length > 0 ? "pass" : "warn",
    message: manifest?.prices.length
      ? `${manifest.prices.length} price(s) configured`
      : "No prices in manifest",
    fix: "stripe-installer run --provision",
  });

  // Database checks
  const dbUrl = await getDatabaseUrl(vault);
  const dbFormat = validateDatabaseUrl(dbUrl);
  checks.push({
    id: "db-url",
    category: "database",
    name: "DATABASE_URL configured",
    status: dbFormat.valid ? "pass" : "warn",
    message: dbFormat.message,
    fix: "stripe-installer vault set DATABASE_URL postgresql://...",
  });

  if (dbUrl && dbFormat.valid) {
    const conn = await testPostgresConnection(dbUrl);
    checks.push({
      id: "db-connection",
      category: "database",
      name: "PostgreSQL connection",
      status: conn.ok ? "pass" : "fail",
      message: conn.message,
      fix: "Verify DATABASE_URL and network access; npm install pg in project",
    });
  }

  const hasSchema = await fileExists(join(root, "db/schema.sql"));
  checks.push({
    id: "db-schema",
    category: "database",
    name: "Database schema file",
    status: hasSchema ? "pass" : "warn",
    message: hasSchema ? "db/schema.sql exists" : "Schema not generated",
    fix: "stripe-installer deploy --generate",
  });

  // Domain & SSL
  const prodUrl = config.productionUrl ?? config.domain;
  checks.push({
    id: "domain-configured",
    category: "domain",
    name: "Production URL configured",
    status: prodUrl ? "pass" : "warn",
    message: prodUrl ?? "No domain/productionUrl in deploy.config.json",
    fix: 'Add "productionUrl": "https://yourdomain.com" to deploy.config.json',
  });

  if (prodUrl?.startsWith("https://")) {
    checks.push({
      id: "ssl-https",
      category: "ssl",
      name: "HTTPS production URL",
      status: "pass",
      message: "Production URL uses HTTPS",
    });

    try {
      const res = await fetch(prodUrl, { method: "HEAD", signal: AbortSignal.timeout(8000) });
      checks.push({
        id: "ssl-reachable",
        category: "ssl",
        name: "Production site reachable",
        status: res.ok || res.status < 500 ? "pass" : "warn",
        message: `HTTP ${res.status} — SSL typically auto-provisioned by host`,
      });
    } catch {
      checks.push({
        id: "ssl-reachable",
        category: "ssl",
        name: "Production site reachable",
        status: "warn",
        message: "Site not reachable yet (deploy first)",
        fix: "Deploy app, then re-run readiness",
      });
    }
  } else {
    checks.push({
      id: "ssl-https",
      category: "ssl",
      name: "HTTPS enabled",
      status: "warn",
      message: "SSL auto-provisioned by Vercel/Railway/Fly.io on deploy",
      fix: "Deploy with HTTPS URL — most platforms handle SSL automatically",
    });
  }

  // Security
  const gitignore = await readGitignore(root);
  checks.push({
    id: "gitignore-env",
    category: "security",
    name: ".env files gitignored",
    status: gitignore.includes(".env") ? "pass" : "fail",
    message: gitignore.includes(".env") ? ".env in .gitignore" : ".env may be committed!",
    fix: "Add .env, .env.local, .stripe-installer/ to .gitignore",
  });

  checks.push({
    id: "no-committed-secrets",
    category: "security",
    name: "No secrets in tracked env files",
    status: profile.detectedSecrets.length === 0 ? "pass" : "fail",
    message: profile.detectedSecrets.length === 0
      ? "No secrets detected in project files"
      : `${profile.detectedSecrets.length} secret(s) found in files`,
    fix: "Move secrets to vault; use .env.example with placeholders only",
  });

  // Monitoring
  const hasHealth = await fileExists(join(root, "app/api/health/route.ts"))
    || await fileExists(join(root, "pages/api/health.ts"));
  checks.push({
    id: "health-endpoint",
    category: "monitoring",
    name: "Health check endpoint",
    status: hasHealth || config.monitoring?.healthCheck !== false ? (hasHealth ? "pass" : "warn") : "warn",
    message: hasHealth ? "/api/health exists" : "Health endpoint not generated",
    fix: "stripe-installer deploy --generate",
  });

  // Backup
  const hasBackup = await fileExists(join(root, "scripts/backup-db.sh"))
    || await fileExists(join(root, "scripts/backup-db.ps1"));
  checks.push({
    id: "backup-script",
    category: "backup",
    name: "Database backup script",
    status: hasBackup || config.backup?.enabled === false ? (hasBackup ? "pass" : "warn") : "warn",
    message: hasBackup ? "Backup scripts exist" : "No backup script",
    fix: "stripe-installer deploy --generate",
  });

  // Deploy platform
  const platform = config.platform ?? await detectDeployPlatform(root, profile);
  checks.push({
    id: "deploy-platform",
    category: "deploy",
    name: "Deployment platform",
    status: platform !== "unknown" ? "pass" : "warn",
    message: platform !== "unknown" ? `Detected: ${platform}` : "Platform not detected",
    fix: "Add vercel.json or set platform in deploy.config.json",
  });

  const hasBuild = profile.hasPackageJson;
  checks.push({
    id: "build-script",
    category: "deploy",
    name: "Build script available",
    status: hasBuild ? "pass" : "warn",
    message: hasBuild ? "package.json with scripts" : "No package.json",
  });

  return checks;
}

export function scoreReadiness(checks: ReadinessCheck[]): number {
  if (checks.length === 0) return 0;
  const weights = { pass: 1, warn: 0.5, fail: 0 };
  const total = checks.reduce((sum, c) => sum + weights[c.status], 0);
  return Math.round((total / checks.length) * 100);
}

export function formatReadinessReport(checks: ReadinessCheck[], score: number): string {
  const lines = [
    `# Production Readiness Report`,
    ``,
    `Score: ${score}/100`,
    ``,
  ];

  const categories = [...new Set(checks.map((c) => c.category))];
  for (const cat of categories) {
    lines.push(`## ${cat.charAt(0).toUpperCase() + cat.slice(1)}`);
    for (const check of checks.filter((c) => c.category === cat)) {
      const icon = check.status === "pass" ? "✓" : check.status === "warn" ? "!" : "✗";
      lines.push(`- [${icon}] **${check.name}**: ${check.message}`);
      if (check.fix && check.status !== "pass") lines.push(`  - Fix: ${check.fix}`);
    }
    lines.push("");
  }

  return lines.join("\n");
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function readGitignore(root: string): Promise<string> {
  try {
    return await readFile(join(root, ".gitignore"), "utf8");
  } catch {
    return "";
  }
}
