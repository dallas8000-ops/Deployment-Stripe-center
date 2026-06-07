import { writeFile, readFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import type { DeployConfig, DeployResult, PostgresProvisionResult, ProjectProfile } from "../types.js";
import type { SecretVault } from "../security/vault.js";
import { z } from "zod";
import { detectDeployPlatform, platformDeployCommand } from "./platform-detector.js";
import { InfraCodeGenerator } from "./infra-generator.js";
import { runReadinessChecks, scoreReadiness, formatReadinessReport } from "./readiness.js";
import { getDatabaseUrl, testPostgresConnection } from "./postgres.js";
import { provisionPostgres } from "./postgres-provisioner.js";
import { runPipeline } from "../stripe/pipeline.js";
import { writeProjectFiles } from "../utils/file-writer.js";
import { resolveAutomationUrls } from "../stripe/config-schema.js";
import { healthCheckPath } from "./framework-deploy.js";
import { resolveWebhookPath } from "../stripe/framework-profiles.js";
import { pushToPlatform } from "./platform-push.js";
import { DEFAULT_SAAS_TIERS } from "../stripe/default-tiers.js";

const deployConfigSchema = z.object({
  domain: z.string().optional(),
  productionUrl: z.string().url().optional(),
  platform: z.enum(["vercel", "railway", "render", "fly", "docker", "unknown"]).optional(),
  postgres: z.object({
    provider: z.enum(["neon", "supabase", "railway", "render", "self-hosted", "unknown"]).optional(),
    connectionEnvVar: z.string().optional(),
    autoProvision: z.boolean().optional(),
    region: z.string().optional(),
    projectName: z.string().optional(),
  }).optional(),
  monitoring: z.object({
    healthCheck: z.boolean().optional(),
    sentry: z.boolean().optional(),
  }).optional(),
  backup: z.object({
    enabled: z.boolean().optional(),
    retentionDays: z.number().optional(),
  }).optional(),
  ssl: z.object({ auto: z.boolean().optional() }).optional(),
});

export function parseDeployConfig(raw: unknown): DeployConfig {
  return deployConfigSchema.parse(raw);
}

export interface DeployPipelineOptions {
  provisionStripe?: boolean;
  generateCode?: boolean;
  generateInfra?: boolean;
  provisionPostgres?: boolean;
  runReadiness?: boolean;
  push?: boolean;
  force?: boolean;
  stripeConfigPath?: string;
  deployConfigPath?: string;
}

export async function runDeployPipeline(
  profile: ProjectProfile,
  vault: SecretVault,
  opts: DeployPipelineOptions = {}
): Promise<DeployResult> {
  const root = profile.rootPath;
  let deployConfig: DeployConfig = {};

  try {
    const raw = JSON.parse(
      await readFile(join(root, opts.deployConfigPath ?? "deploy.config.json"), "utf8")
    );
    deployConfig = parseDeployConfig(raw);
  } catch {
    // use defaults
  }

  const platform = deployConfig.platform ?? await detectDeployPlatform(root, profile);
  const productionUrl = deployConfig.productionUrl
    ?? (deployConfig.domain ? `https://${deployConfig.domain}` : undefined);

  const filesGenerated: string[] = [];
  const nextSteps: string[] = [];

  // 1. Stripe setup
  if (opts.provisionStripe !== false || opts.generateCode !== false) {
    let stripeConfig = resolveAutomationUrls(
      { tiers: DEFAULT_SAAS_TIERS, appUrl: productionUrl ?? "http://localhost:3000" },
      profile,
      productionUrl ?? "http://localhost:3000"
    );

    try {
      const stripeRaw = JSON.parse(
        await readFile(join(root, opts.stripeConfigPath ?? "stripe.config.json"), "utf8")
      );
      stripeConfig = resolveAutomationUrls(
        { ...stripeRaw, appUrl: productionUrl ?? stripeRaw.appUrl },
        profile,
        productionUrl ?? "http://localhost:3000"
      );
      if (productionUrl) {
        const webhookPath = resolveWebhookPath(profile);
        stripeConfig.webhookUrl = `${productionUrl}${webhookPath}`;
        stripeConfig.billingPortalReturnUrl = `${productionUrl}/account`;
      }
    } catch {
      if (productionUrl) {
        const webhookPath = resolveWebhookPath(profile);
        stripeConfig.webhookUrl = `${productionUrl}${webhookPath}`;
        stripeConfig.billingPortalReturnUrl = `${productionUrl}/account`;
      }
    }

    const pipelineResult = await runPipeline(profile, vault, {
      provision: opts.provisionStripe !== false,
      generate: opts.generateCode !== false,
      force: opts.force,
      config: stripeConfig,
      appUrl: productionUrl,
    });

    pipelineResult.files?.filter((f) => f.action !== "skipped").forEach((f) => {
      filesGenerated.push(f.path);
    });
  }

  // 2. Infrastructure (postgres, monitoring, backup, domain/ssl docs)
  let postgresProvisioned: PostgresProvisionResult | undefined;
  if (opts.generateInfra !== false) {
    const infra = new InfraCodeGenerator(profile, deployConfig, platform);
    const infraFiles = infra.generateAll();
    const results = await writeProjectFiles(root, infraFiles, { force: opts.force });
    results.filter((r) => r.action !== "skipped").forEach((r) => {
      filesGenerated.push(r.path);
    });
  }

  // 2b. Auto-provision PostgreSQL (Neon / Supabase API)
  const shouldProvisionDb = opts.provisionPostgres === true
    || (opts.provisionPostgres !== false && deployConfig.postgres?.autoProvision);
  if (shouldProvisionDb) {
    try {
      postgresProvisioned = await provisionPostgres(root, vault, deployConfig, {
        projectName: deployConfig.postgres?.projectName ?? profile.name,
        provider: deployConfig.postgres?.provider,
        region: deployConfig.postgres?.region,
        applySchema: true,
      });
    } catch (err) {
      nextSteps.push(`PostgreSQL provisioning failed: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }

  // 3. Production readiness
  const readiness = opts.runReadiness !== false
    ? await runReadinessChecks(profile, vault, { ...deployConfig, productionUrl })
    : [];

  const readinessScore = scoreReadiness(readiness);

  // Save readiness report
  if (readiness.length > 0) {
    const report = formatReadinessReport(readiness, readinessScore);
    const reportPath = join(root, "deploy", "READINESS-REPORT.md");
    await mkdir(join(root, "deploy"), { recursive: true });
    await writeFile(reportPath, report, "utf8");
    filesGenerated.push("deploy/READINESS-REPORT.md");
  }

  // Save deploy manifest
  const manifest = {
    deployedAt: new Date().toISOString(),
    platform,
    productionUrl,
    domain: deployConfig.domain,
    postgresProvider: deployConfig.postgres?.provider,
    readinessScore,
  };
  await mkdir(join(root, ".stripe-installer"), { recursive: true });
  await writeFile(
    join(root, ".stripe-installer", "deploy-manifest.json"),
    JSON.stringify(manifest, null, 2),
    "utf8"
  );

  // Postgres connection status
  let postgresConnected: boolean | undefined;
  const dbUrl = await getDatabaseUrl(vault);
  if (dbUrl) {
    const conn = await testPostgresConnection(dbUrl);
    postgresConnected = conn.ok;
    if (!conn.ok) nextSteps.push(`Fix PostgreSQL: ${conn.message}`);
    else if (postgresProvisioned?.schemaApplied) {
      nextSteps.push(`PostgreSQL: ${postgresProvisioned.message}`);
    }
  } else if (!postgresProvisioned) {
    nextSteps.push("Provision PostgreSQL: deploy --provision-db or vault set DATABASE_URL");
    nextSteps.push("Apply schema: stripe-installer postgres apply-schema");
  }

  if (readinessScore < 80) {
    nextSteps.push(`Improve readiness score (${readinessScore}/100) — see deploy/READINESS-REPORT.md`);
  }

  if (!productionUrl) {
    nextSteps.push('Set productionUrl in deploy.config.json');
  } else {
    nextSteps.push(`Deploy: ${platformDeployCommand(platform)}`);
    nextSteps.push(`Verify: curl ${productionUrl}${healthCheckPath(profile.framework)}`);
  }

  nextSteps.push("Schedule backups: scripts/backup-db.sh (cron) or backup-db.ps1 (Task Scheduler)");

  let pushResult: { success: boolean; message: string } | undefined;
  if (opts.push && productionUrl) {
    pushResult = pushToPlatform(root, platform);
    if (pushResult.success) {
      nextSteps.unshift(`Platform deploy: ${pushResult.message}`);
    } else {
      nextSteps.unshift(`Platform deploy failed: ${pushResult.message}`);
    }
  } else if (opts.push && !productionUrl) {
    nextSteps.unshift("Set productionUrl in deploy.config.json before --push");
  }

  return {
    platform,
    readiness,
    readinessScore,
    filesGenerated,
    postgresConnected,
    postgresProvisioned,
    productionUrl,
    nextSteps,
    pushResult,
  };
}
