#!/usr/bin/env node
import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { resolve, join } from "node:path";
import { readFile } from "node:fs/promises";
import { ProjectScanner } from "./scanner/project-scanner.js";
import { SecretVault } from "./security/vault.js";
import { StripeSetupEngine } from "./stripe/setup-engine.js";
import { StripeApiAutomation } from "./stripe/api-automation.js";
import { StripeCodeGenerator } from "./stripe/code-generator.js";
import { verifyApiKeys } from "./stripe/stripe-client.js";
import { DEFAULT_SAAS_TIERS } from "./stripe/default-tiers.js";
import { parseStripeConfig, resolveAutomationUrls } from "./stripe/config-schema.js";
import { importEnvToVault, syncVaultToEnv, findEnvFile } from "./stripe/env-sync.js";
import { runPipeline, loadConfigFromJson } from "./stripe/pipeline.js";
import { writeProjectFiles } from "./utils/file-writer.js";
import { AIOrchestrator, createAIProvider } from "./ai/orchestrator.js";
import { runDeployPipeline, parseDeployConfig } from "./deploy/deploy-pipeline.js";
import { runReadinessChecks, scoreReadiness } from "./deploy/readiness.js";
import { detectDeployPlatform } from "./deploy/platform-detector.js";
import { provisionPostgres, getPostgresProvisionStatus } from "./deploy/postgres-provisioner.js";
import { applyPostgresSchema, getDatabaseUrl } from "./deploy/postgres.js";
import { hasAIProvider } from "./ai/orchestrator.js";
import { runStripeDiagnostics } from "./stripe/diagnostics.js";
import { runAutoFix, runStripeRepair } from "./stripe/repair.js";
import type { StripeFixAction } from "./types.js";

const program = new Command();

program
  .name("stripe-installer")
  .description("AI-assisted Stripe setup with secure secret isolation")
  .version("0.5.0");

async function openVault(root: string): Promise<SecretVault> {
  const vault = new SecretVault(root);
  const envPass = process.env.STRIPE_INSTALLER_PASSPHRASE;
  if (envPass) {
    await vault.initialize(envPass);
    return vault;
  }
  const rl = createInterface({ input, output });
  const passphrase = await rl.question("Vault passphrase: ");
  await vault.initialize(passphrase);
  rl.close();
  return vault;
}

program
  .command("scan")
  .description("Scan a project and detect Stripe setup needs")
  .argument("[path]", "Project directory", ".")
  .action(async (path: string) => {
    const root = resolve(path);
    const spinner = ora("Scanning project...").start();
    const profile = await new ProjectScanner(root).scan();
    spinner.succeed("Scan complete");

    console.log(chalk.bold("\nProject Profile"));
    console.log(chalk.dim("─".repeat(40)));
    console.log(`  Name:       ${profile.name}`);
    console.log(`  Framework:  ${profile.framework}${profile.nextRouter ? ` (${profile.nextRouter} router)` : ""}`);
    console.log(`  Language:   ${profile.language}`);
    console.log(`  Stripe:     ${profile.existingStripeCode ? "detected" : "not found"}`);
    console.log(`  Features:   ${profile.suggestedFeatures.join(", ")}`);

    if (profile.detectedSecrets.length > 0) {
      console.log(chalk.yellow(`\n  Secrets (redacted): ${profile.detectedSecrets.length}`));
    }
    for (const rec of profile.recommendations) {
      console.log(`  • ${rec}`);
    }
  });

program
  .command("vault")
  .description("Manage encrypted secret vault")
  .argument("<action>", "init | set | list | import")
  .argument("[key]", "Secret key name")
  .argument("[value]", "Secret value")
  .option("-p, --path <path>", "Project directory", ".")
  .option("--env <file>", "Env file for import", ".env.local")
  .action(async (action: string, key?: string, value?: string, opts?: { path: string; env: string }) => {
    const root = resolve(opts?.path ?? ".");
    const vault = new SecretVault(root);
    const rl = createInterface({ input, output });

    if (action === "init") {
      const passphrase =
        process.env.STRIPE_INSTALLER_PASSPHRASE ?? (await rl.question("Vault passphrase: "));
      await vault.initialize(passphrase);
      rl.close();
      console.log(chalk.green("Vault initialized at .stripe-installer/"));
      return;
    }

    const passphrase =
      process.env.STRIPE_INSTALLER_PASSPHRASE ?? (await rl.question("Vault passphrase: "));
    await vault.initialize(passphrase);

    if (action === "set" && key) {
      const secretValue = value ?? (await rl.question(`Value for ${key}: `));
      await vault.set(key, secretValue);
      rl.close();
      console.log(chalk.green(`Stored ${key} in encrypted vault.`));
      return;
    }

    if (action === "list") {
      const keys = await vault.listKeys();
      rl.close();
      console.log(chalk.bold("Vault keys:"));
      keys.forEach((k) => console.log(`  • ${k}`));
      return;
    }

    if (action === "import") {
      rl.close();
      const envFile = opts?.env ?? (await findEnvFile(root)) ?? ".env.local";
      const imported = await importEnvToVault(root, vault, envFile);
      console.log(chalk.green(`Imported ${imported.length} key(s) from ${envFile}:`));
      imported.forEach((k) => console.log(`  • ${k}`));
      return;
    }

    rl.close();
    console.log(chalk.red("Unknown action. Use: init, set, list, import"));
  });

program
  .command("verify")
  .description("Verify Stripe API keys")
  .argument("[path]", "Project directory", ".")
  .option("-p, --path <path>", "Project directory (alias)")
  .action(async (path: string, opts: { path?: string }) => {
    const vault = await openVault(resolve(opts.path ?? path));
    const spinner = ora("Verifying...").start();
    const result = await verifyApiKeys(vault);
    spinner.succeed(result.secretKey.valid ? "Keys verified" : "Verification failed");

    console.log(`  Secret:      ${statusBadge(result.secretKey.valid)} ${result.secretKey.message}`);
    console.log(`  Publishable: ${statusBadge(result.publishableKey.valid)} ${result.publishableKey.message}`);
    if (result.accountName) console.log(`  Account:     ${result.accountName}`);
    if (result.country) console.log(`  Country:     ${result.country}`);
    if (result.billingEnabled !== undefined) {
      console.log(`  Billing:     ${result.billingEnabled ? chalk.green("enabled") : chalk.yellow("check dashboard")}`);
    }
  });

program
  .command("status")
  .description("Show project Stripe setup status")
  .argument("[path]", "Project directory", ".")
  .option("-p, --path <path>", "Project directory (alias)")
  .action(async (path: string, opts: { path?: string }) => {
    const root = resolve(opts.path ?? path);
    const profile = await new ProjectScanner(root).scan();
    const automation = new StripeApiAutomation(root, new SecretVault(root));
    const manifest = await automation.loadManifest();

    console.log(chalk.bold("\nStripe Installer Status"));
    console.log(chalk.dim("─".repeat(40)));
    console.log(`  Project:    ${profile.name} (${profile.framework})`);
    console.log(`  Stripe code: ${profile.existingStripeCode ? "yes" : "no"}`);

    if (manifest) {
      console.log(chalk.bold("\n  Manifest"));
      console.log(`  Updated:    ${manifest.updatedAt}`);
      console.log(`  Products:   ${manifest.products.length}`);
      console.log(`  Prices:     ${manifest.prices.map((p) => `${p.tier} (${p.id})`).join(", ") || "none"}`);
      if (manifest.webhookEndpoint) console.log(`  Webhook:    ${manifest.webhookEndpoint.url}`);
      if (manifest.billingPortalConfig) console.log(`  Portal:     ${manifest.billingPortalConfig.id}`);
    } else {
      console.log(chalk.dim("\n  No manifest — run: stripe-installer run"));
    }

    try {
      const vault = await openVault(root);
      const keys = await vault.listKeys();
      console.log(chalk.bold("\n  Vault keys:"), keys.join(", ") || "(empty)");
    } catch {
      console.log(chalk.dim("\n  Vault locked or not initialized"));
    }
  });

program
  .command("sync-env")
  .description("Write vault secrets to .env.local (never logged)")
  .argument("[path]", "Project directory", ".")
  .option("-p, --path <path>", "Project directory (alias)")
  .action(async (path: string, opts: { path?: string }) => {
    const root = resolve(opts.path ?? path);
    const vault = await openVault(root);
    const synced = await syncVaultToEnv(root, vault);
    console.log(chalk.green(`Synced ${synced.length} key(s) to .env.local`));
    synced.forEach((k) => console.log(`  • ${k}`));
  });

program
  .command("run")
  .description("Full pipeline: verify → provision → generate → sync env")
  .argument("[path]", "Project directory", ".")
  .option("--no-provision", "Skip Stripe API provisioning")
  .option("--no-generate", "Skip code generation")
  .option("--sync-env", "Write vault secrets to .env.local")
  .option("--force", "Overwrite existing generated files")
  .option("--config <file>", "Config file", "stripe.config.json")
  .option("--app-url <url>", "App URL", "http://localhost:3000")
  .action(async (path: string, opts: {
    provision: boolean;
    generate: boolean;
    syncEnv?: boolean;
    force?: boolean;
    config: string;
    appUrl: string;
  }) => {
    const root = resolve(path);
    const vault = await openVault(root);
    const profile = await new ProjectScanner(root).scan();

    let config;
    try {
      const raw = JSON.parse(await readFile(join(root, opts.config), "utf8"));
      config = loadConfigFromJson(raw, opts.appUrl);
      console.log(chalk.dim(`Config: ${opts.config}`));
    } catch {
      config = { tiers: DEFAULT_SAAS_TIERS, appUrl: opts.appUrl };
      console.log(chalk.dim("Using default SaaS tiers"));
    }

    const spinner = ora("Running Stripe setup pipeline...").start();
    try {
      const result = await runPipeline(profile, vault, {
        provision: opts.provision,
        generate: opts.generate,
        syncEnv: opts.syncEnv,
        force: opts.force,
        config,
        appUrl: opts.appUrl,
      });
      spinner.succeed("Pipeline complete");

      if (result.provision) {
        console.log(chalk.bold("\nProvisioned"));
        result.provision.prices.forEach((p) => {
          const tag = p.reused ? chalk.dim("(reused)") : chalk.green("(new)");
          console.log(`  ${p.tier}: ${p.id} ${tag}`);
        });
        result.provision.warnings.forEach((w) => console.log(chalk.yellow(`  ⚠ ${w}`)));
      }

      if (result.files) {
        console.log(chalk.bold("\nFiles"));
        result.files.forEach((f) => {
          const color = f.action === "skipped" ? chalk.dim : chalk.green;
          console.log(color(`  ${f.action === "created" ? "+" : f.action === "updated" ? "~" : "·"} ${f.path}`));
        });
      }

      console.log(chalk.dim("\nLocal webhooks: stripe listen --forward-to localhost:3000/api/stripe/webhook"));
    } catch (err) {
      spinner.fail(err instanceof Error ? err.message : "Pipeline failed");
      process.exit(1);
    }
  });

program
  .command("automate")
  .description("Provision Stripe resources and/or generate code")
  .argument("[path]", "Project directory", ".")
  .option("--provision", "Create products, prices, webhooks, portal")
  .option("--generate", "Generate integration code")
  .option("--force", "Overwrite existing files")
  .option("--config <file>", "Config file", "stripe.config.json")
  .option("--app-url <url>", "App URL", "http://localhost:3000")
  .action(async (path: string, opts: {
    provision?: boolean;
    generate?: boolean;
    force?: boolean;
    config: string;
    appUrl: string;
  }) => {
    const root = resolve(path);
    const vault = await openVault(root);
    const profile = await new ProjectScanner(root).scan();
    const automation = new StripeApiAutomation(root, vault);

    let config = resolveAutomationUrls(
      { tiers: DEFAULT_SAAS_TIERS, appUrl: opts.appUrl },
      profile,
      opts.appUrl
    );

    try {
      const raw = JSON.parse(await readFile(join(root, opts.config), "utf8"));
      config = resolveAutomationUrls(parseStripeConfig(raw), profile, opts.appUrl);
    } catch {
      // defaults
    }

    const doProvision = opts.provision || (!opts.provision && !opts.generate);
    const doGenerate = opts.generate || (!opts.provision && !opts.generate);

    if (doProvision) {
      const spinner = ora("Provisioning...").start();
      try {
        const result = await automation.run(config);
        spinner.succeed("Provisioned");
        result.products.forEach((p) => console.log(`  Product: ${p.name} ${p.reused ? "(reused)" : "(new)"}`));
        result.prices.forEach((p) => console.log(`  Price: ${p.tier} — ${p.id}`));
        result.warnings.forEach((w) => console.log(chalk.yellow(`  ⚠ ${w}`)));
      } catch (err) {
        spinner.fail(err instanceof Error ? err.message : "Failed");
        process.exit(1);
      }
    }

    if (doGenerate) {
      const manifest = await automation.loadManifest();
      const files = new StripeCodeGenerator(profile).generateAll(manifest);
      const results = await writeProjectFiles(root, files, { force: opts.force });
      console.log(chalk.bold("\nGenerated"));
      results.filter((r) => r.action !== "skipped").forEach((r) => {
        console.log(chalk.green(`  ${r.action === "updated" ? "~" : "+"} ${r.path}`));
      });
      const skipped = results.filter((r) => r.action === "skipped").length;
      if (skipped) console.log(chalk.dim(`  (${skipped} skipped — use --force to overwrite)`));
    }
  });

program
  .command("setup")
  .description("Generate setup plan and apply boilerplate")
  .argument("[path]", "Project directory", ".")
  .option("--validate", "Verify API keys")
  .option("--apply", "Write generated files")
  .option("--ai", "AI recommendations")
  .action(async (path: string, opts: { validate?: boolean; apply?: boolean; ai?: boolean }) => {
    const root = resolve(path);
    const profile = await new ProjectScanner(root).scan();
    const vault = await openVault(root);
    const engine = new StripeSetupEngine(profile, vault);
    const plan = engine.buildPlan();

    console.log(chalk.bold("\nSetup Plan"));
    console.log(`  Features: ${plan.features.join(", ")}`);
    plan.filesToCreate.forEach((f) => console.log(`  + ${f.path}`));

    if (opts.ai) {
      const provider = (await hasAIProvider(vault)) ? createAIProvider(vault) : undefined;
      const recs = await new AIOrchestrator(profile, vault, provider).generateRecommendations();
      console.log("\n" + recs);
    }

    if (opts.validate) {
      const r = await engine.validateConnection();
      console.log(r.ok ? chalk.green(r.message) : chalk.red(r.message));
    }

    if (opts.apply) {
      const created = await engine.applyPlan(plan);
      created.forEach((f) => console.log(chalk.green(`  + ${f}`)));
    }
  });

program
  .command("diagnose")
  .description("Diagnose Stripe setup issues in a project")
  .argument("[path]", "Project directory", ".")
  .option("--skip-vault", "Skip vault/API checks")
  .action(async (path: string, opts: { skipVault?: boolean }) => {
    const root = resolve(path);
    const profile = await new ProjectScanner(root).scan();

    let vault: SecretVault | null = null;
    if (!opts.skipVault) {
      try {
        vault = await openVault(root);
      } catch {
        console.log(chalk.yellow("Vault locked — run with unlocked vault for full diagnosis\n"));
      }
    }

    const spinner = ora("Diagnosing Stripe setup...").start();
    const report = await runStripeDiagnostics(profile, vault);
    spinner.succeed(`Health score: ${report.healthScore}/100`);

    console.log(chalk.dim(`\n${report.summary}\n`));

    const categories = [...new Set(report.issues.map((i) => i.category))];
    for (const cat of categories) {
      console.log(chalk.bold(cat.charAt(0).toUpperCase() + cat.slice(1)));
      for (const issue of report.issues.filter((i) => i.category === cat)) {
        const icon =
          issue.severity === "error" ? chalk.red("✗") :
          issue.severity === "warning" ? chalk.yellow("!") : chalk.blue("·");
        const fixTag = issue.autoFixable ? chalk.green(" [auto-fix]") : "";
        console.log(`  ${icon} ${issue.title}${fixTag}`);
        console.log(chalk.dim(`      ${issue.message}`));
        console.log(chalk.dim(`      → ${issue.fixHint}`));
      }
      console.log();
    }

    const fixable = report.issues.filter((i) => i.autoFixable).length;
    if (fixable > 0) {
      console.log(chalk.cyan(`Run: stripe-installer fix --all`));
    }
  });

program
  .command("fix")
  .description("Auto-fix Stripe setup issues")
  .argument("[path]", "Project directory", ".")
  .option("--all", "Fix all auto-fixable issues")
  .option("--issue <id>", "Fix a specific issue (repeatable)", (v, arr: string[]) => [...arr, v], [])
  .option("--action <action>", "Run a specific repair action")
  .option("--force", "Overwrite existing files when generating")
  .action(async (path: string, opts: {
    all?: boolean;
    issue: string[];
    action?: string;
    force?: boolean;
  }) => {
    const root = resolve(path);
    const profile = await new ProjectScanner(root).scan();
    const vault = await openVault(root);

    if (opts.action) {
      const spinner = ora(`Running ${opts.action}...`).start();
      try {
        const result = await runStripeRepair(profile, vault, opts.action as StripeFixAction);
        if (result.success) spinner.succeed(result.message);
        else {
          spinner.fail(result.message);
          process.exit(1);
        }
        if (result.files?.length) result.files.forEach((f) => console.log(chalk.green(`  + ${f}`)));
      } catch (err) {
        spinner.fail(err instanceof Error ? err.message : "Fix failed");
        process.exit(1);
      }
      return;
    }

    if (!opts.all && opts.issue.length === 0) {
      console.log(chalk.red("Specify --all, --issue <id>, or --action <name>"));
      process.exit(1);
    }

    const spinner = ora("Applying fixes...").start();
    try {
      const results = await runAutoFix(profile, vault, {
        issueIds: opts.issue.length ? opts.issue : undefined,
        force: opts.force,
      });
      const ok = results.filter((r) => r.success);
      const fail = results.filter((r) => !r.success);
      spinner.succeed(`Applied ${ok.length} fix(es)${fail.length ? `, ${fail.length} failed` : ""}`);

      for (const r of results) {
        const color = r.success ? chalk.green : chalk.red;
        console.log(color(`  ${r.success ? "✓" : "✗"} ${r.action}: ${r.message}`));
        r.files?.forEach((f) => console.log(chalk.dim(`      + ${f}`)));
      }

      const after = await runStripeDiagnostics(profile, vault);
      console.log(chalk.bold(`\nHealth after fix: ${after.healthScore}/100`));
    } catch (err) {
      spinner.fail(err instanceof Error ? err.message : "Fix failed");
      process.exit(1);
    }
  });

program
  .command("readiness")
  .description("Run production readiness checks")
  .argument("[path]", "Project directory", ".")
  .option("-p, --path <path>", "Project directory (alias)")
  .option("--config <file>", "Deploy config", "deploy.config.json")
  .action(async (path: string, opts: { path?: string; config: string }) => {
    const root = resolve(opts.path ?? path);
    const profile = await new ProjectScanner(root).scan();
    const vault = await openVault(root);

    let deployConfig = {};
    try {
      deployConfig = parseDeployConfig(JSON.parse(await readFile(join(root, opts.config), "utf8")));
    } catch {
      // defaults
    }

    const spinner = ora("Running readiness checks...").start();
    const checks = await runReadinessChecks(profile, vault, deployConfig);
    const score = scoreReadiness(checks);
    spinner.succeed(`Readiness score: ${score}/100`);

    const categories = [...new Set(checks.map((c) => c.category))];
    for (const cat of categories) {
      console.log(chalk.bold(`\n${cat.charAt(0).toUpperCase() + cat.slice(1)}`));
      for (const check of checks.filter((c) => c.category === cat)) {
        const icon = check.status === "pass" ? chalk.green("✓") : check.status === "warn" ? chalk.yellow("!") : chalk.red("✗");
        console.log(`  ${icon} ${check.name}: ${check.message}`);
        if (check.fix && check.status !== "pass") console.log(chalk.dim(`      → ${check.fix}`));
      }
    }

    if (score >= 80) {
      console.log(chalk.green("\nReady for production deployment"));
    } else if (score >= 50) {
      console.log(chalk.yellow("\nAlmost ready — address warnings above"));
    } else {
      console.log(chalk.red("\nNot production ready — fix failures first"));
    }
  });

program
  .command("postgres")
  .description("PostgreSQL provisioning and schema management")
  .argument("<action>", "provision | apply-schema | status")
  .option("-p, --path <path>", "Project directory", ".")
  .option("--provider <provider>", "neon | supabase", "neon")
  .option("--region <region>", "Cloud region")
  .option("--name <name>", "Database project name")
  .option("--no-schema", "Skip applying db/schema.sql after provision")
  .option("--deploy-config <file>", "Deploy config", "deploy.config.json")
  .action(async (action: string, opts: {
    path: string;
    provider: string;
    region?: string;
    name?: string;
    schema: boolean;
    deployConfig: string;
  }) => {
    const root = resolve(opts.path);
    const vault = await openVault(root);
    const profile = await new ProjectScanner(root).scan();

    let deployConfig = {};
    try {
      deployConfig = parseDeployConfig(JSON.parse(await readFile(join(root, opts.deployConfig), "utf8")));
    } catch {
      // defaults
    }

    if (action === "status") {
      const status = await getPostgresProvisionStatus(root, vault);
      console.log(chalk.bold("\nPostgreSQL Status"));
      console.log(`  Connected: ${status.connected ? chalk.green("yes") : chalk.yellow("no")}`);
      console.log(`  ${status.message}`);
      if (status.manifest) {
        console.log(`  Provider:  ${status.manifest.provider}`);
        console.log(`  Since:     ${status.manifest.provisionedAt}`);
      }
      return;
    }

    if (action === "apply-schema") {
      const dbUrl = await getDatabaseUrl(vault);
      if (!dbUrl) {
        console.log(chalk.red("DATABASE_URL not in vault"));
        process.exit(1);
      }
      const spinner = ora("Applying schema...").start();
      const result = await applyPostgresSchema(root, dbUrl);
      if (result.ok) spinner.succeed(result.message);
      else {
        spinner.fail(result.message);
        process.exit(1);
      }
      return;
    }

    if (action === "provision") {
      const spinner = ora(`Provisioning ${opts.provider} database...`).start();
      try {
        const result = await provisionPostgres(root, vault, deployConfig, {
          projectName: opts.name ?? profile.name,
          provider: opts.provider as "neon" | "supabase",
          region: opts.region,
          applySchema: opts.schema,
        });
        spinner.succeed(result.message);
        console.log(`  Provider: ${result.provider}`);
        console.log(`  Reused:   ${result.reused ? "yes" : "no"}`);
        console.log(`  Schema:   ${result.schemaApplied ? "applied" : "not applied"}`);
        if (result.projectId) console.log(`  Project:  ${result.projectId}`);
        if (result.projectRef) console.log(`  Ref:      ${result.projectRef}`);
      } catch (err) {
        spinner.fail(err instanceof Error ? err.message : "Provision failed");
        process.exit(1);
      }
      return;
    }

    console.log(chalk.red("Unknown action. Use: provision, apply-schema, status"));
  });

program
  .command("deploy")
  .description("One-click production setup: Stripe + PostgreSQL + monitoring + backup + readiness")
  .argument("[path]", "Project directory", ".")
  .option("--no-stripe", "Skip Stripe provisioning")
  .option("--no-generate", "Skip Stripe code generation")
  .option("--no-infra", "Skip infra file generation")
  .option("--provision-db", "Auto-provision PostgreSQL via Neon/Supabase API")
  .option("--push", "Run platform deploy command after pipeline (vercel/railway/fly)")
  .option("--force", "Overwrite existing files")
  .option("--stripe-config <file>", "Stripe config", "stripe.config.json")
  .option("--deploy-config <file>", "Deploy config", "deploy.config.json")
  .action(async (path: string, opts: {
    stripe: boolean;
    generate: boolean;
    infra: boolean;
    provisionDb?: boolean;
    push?: boolean;
    force?: boolean;
    stripeConfig: string;
    deployConfig: string;
  }) => {
    const root = resolve(path);
    const vault = await openVault(root);
    const profile = await new ProjectScanner(root).scan();
    const platform = await detectDeployPlatform(root, profile);

    console.log(chalk.bold("\nOne-Click Production Deploy"));
    console.log(chalk.dim("─".repeat(40)));
    console.log(`  Project:  ${profile.name}`);
    console.log(`  Platform: ${platform}`);
    console.log(`  Steps:    Stripe → PostgreSQL → Domain/SSL → Monitoring → Backup → Readiness`);

    const spinner = ora("Running deployment pipeline...").start();
    try {
      const result = await runDeployPipeline(profile, vault, {
        provisionStripe: opts.stripe,
        generateCode: opts.generate,
        generateInfra: opts.infra,
        provisionPostgres: opts.provisionDb,
        push: opts.push,
        force: opts.force,
        stripeConfigPath: opts.stripeConfig,
        deployConfigPath: opts.deployConfig,
      });

      spinner.succeed(`Deploy pipeline complete — readiness ${result.readinessScore}/100`);

      if (result.filesGenerated.length > 0) {
        console.log(chalk.bold("\nGenerated"));
        result.filesGenerated.forEach((f) => console.log(chalk.green(`  + ${f}`)));
      }

      const fails = result.readiness.filter((c) => c.status === "fail");
      const warns = result.readiness.filter((c) => c.status === "warn");
      if (fails.length) console.log(chalk.red(`\n${fails.length} check(s) failed`));
      if (warns.length) console.log(chalk.yellow(`${warns.length} warning(s)`));

      if (result.postgresProvisioned) {
        console.log(`  PostgreSQL: ${result.postgresProvisioned.message}`);
      } else if (result.postgresConnected !== undefined) {
        console.log(`  PostgreSQL: ${result.postgresConnected ? chalk.green("connected") : chalk.yellow("not connected")}`);
      }

      if (result.pushResult) {
        if (result.pushResult.success) console.log(chalk.green(`\n  Push: ${result.pushResult.message}`));
        else console.log(chalk.yellow(`\n  Push: ${result.pushResult.message}`));
      }

      console.log(chalk.bold("\nNext steps"));
      result.nextSteps.forEach((s) => console.log(`  → ${s}`));
    } catch (err) {
      spinner.fail(err instanceof Error ? err.message : "Deploy failed");
      process.exit(1);
    }
  });

function statusBadge(ok: boolean): string {
  return ok ? chalk.green("✓") : chalk.red("✗");
}

program.parse();
