import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ProjectScanner } from "../scanner/project-scanner.js";
import { SecretVault } from "../security/vault.js";
import { verifyApiKeys } from "../stripe/stripe-client.js";
import { StripeApiAutomation } from "../stripe/api-automation.js";
import { runPipeline, loadConfigFromJson } from "../stripe/pipeline.js";
import { DEFAULT_SAAS_TIERS } from "../stripe/default-tiers.js";
import { runDeployPipeline, parseDeployConfig } from "../deploy/deploy-pipeline.js";
import { runReadinessChecks, scoreReadiness } from "../deploy/readiness.js";
import { detectDeployPlatform } from "../deploy/platform-detector.js";
import {
  provisionPostgres,
  getPostgresProvisionStatus,
  type PostgresManifest,
} from "../deploy/postgres-provisioner.js";
import { runStripeDiagnostics } from "../stripe/diagnostics.js";
import { runAutoFix, runStripeRepair } from "../stripe/repair.js";
import type {
  DeployConfig,
  KeyVerificationResult,
  ProjectProfile,
  ReadinessCheck,
  StripeDiagnosticReport,
  StripeFixAction,
  StripeManifest,
  StripeRepairResult,
} from "../types.js";

export interface GuiState {
  projectPath: string | null;
  vaultInitialized: boolean;
  vaultUnlocked: boolean;
  vaultKeys: string[];
}

export interface ScanSummary {
  profile: ProjectProfile;
}

export interface StatusSummary {
  profile: ProjectProfile;
  manifest: StripeManifest | null;
  vaultKeys: string[];
  platform: string;
}

function sanitizeProfile(profile: ProjectProfile): ProjectProfile {
  return {
    ...profile,
    detectedSecrets: profile.detectedSecrets.map((s) => ({
      ...s,
      placeholder: s.placeholder,
    })),
  };
}

export class InstallerService {
  private projectPath: string | null = null;
  private vault: SecretVault | null = null;

  getState(): GuiState {
    return {
      projectPath: this.projectPath,
      vaultInitialized: Boolean(this.vault),
      vaultUnlocked: Boolean(this.vault),
      vaultKeys: [],
    };
  }

  setProject(path: string): void {
    this.projectPath = path;
    this.vault = null;
  }

  private requireProject(): string {
    if (!this.projectPath) throw new Error("No project selected");
    return this.projectPath;
  }

  private requireVault(): SecretVault {
    if (!this.vault) throw new Error("Vault is locked — unlock or initialize first");
    return this.vault;
  }

  async initVault(passphrase: string): Promise<{ keys: string[] }> {
    const root = this.requireProject();
    const vault = new SecretVault(root);
    await vault.initialize(passphrase);
    this.vault = vault;
    return { keys: await vault.listKeys() };
  }

  async unlockVault(passphrase: string): Promise<{ keys: string[] }> {
    const root = this.requireProject();
    const vault = new SecretVault(root);
    await vault.initialize(passphrase);
    await vault.listKeys();
    this.vault = vault;
    return { keys: await vault.listKeys() };
  }

  lockVault(): void {
    this.vault = null;
  }

  async listVaultKeys(): Promise<string[]> {
    return this.requireVault().listKeys();
  }

  async setVaultSecret(key: string, value: string): Promise<void> {
    await this.requireVault().set(key, value);
  }

  async scan(): Promise<ScanSummary> {
    const root = this.requireProject();
    const profile = sanitizeProfile(await new ProjectScanner(root).scan());
    return { profile };
  }

  async verify(): Promise<KeyVerificationResult> {
    return verifyApiKeys(this.requireVault());
  }

  async getStatus(): Promise<StatusSummary> {
    const root = this.requireProject();
    const profile = sanitizeProfile(await new ProjectScanner(root).scan());
    const automation = new StripeApiAutomation(root, new SecretVault(root));
    const manifest = await automation.loadManifest();
    const platform = await detectDeployPlatform(root, profile);

    let vaultKeys: string[] = [];
    try {
      vaultKeys = this.vault ? await this.vault.listKeys() : [];
    } catch {
      vaultKeys = [];
    }

    return { profile, manifest, vaultKeys, platform };
  }

  async runStripePipeline(opts: {
    provision?: boolean;
    generate?: boolean;
    syncEnv?: boolean;
    force?: boolean;
    appUrl?: string;
  }) {
    const root = this.requireProject();
    const vault = this.requireVault();
    const profile = await new ProjectScanner(root).scan();

    let config;
    try {
      const raw = JSON.parse(await readFile(join(root, "stripe.config.json"), "utf8"));
      config = loadConfigFromJson(raw, opts.appUrl ?? "http://localhost:3000");
    } catch {
      config = { tiers: DEFAULT_SAAS_TIERS, appUrl: opts.appUrl ?? "http://localhost:3000" };
    }

    return runPipeline(profile, vault, {
      provision: opts.provision !== false,
      generate: opts.generate !== false,
      syncEnv: opts.syncEnv,
      force: opts.force,
      config,
      appUrl: opts.appUrl,
    });
  }

  async deploy(opts: {
    provisionStripe?: boolean;
    generateCode?: boolean;
    generateInfra?: boolean;
    provisionPostgres?: boolean;
    force?: boolean;
  }) {
    const root = this.requireProject();
    const vault = this.requireVault();
    const profile = await new ProjectScanner(root).scan();

    return runDeployPipeline(profile, vault, {
      provisionStripe: opts.provisionStripe !== false,
      generateCode: opts.generateCode !== false,
      generateInfra: opts.generateInfra !== false,
      provisionPostgres: opts.provisionPostgres,
      force: opts.force,
    });
  }

  async readiness(): Promise<{ checks: ReadinessCheck[]; score: number }> {
    const root = this.requireProject();
    const vault = this.requireVault();
    const profile = await new ProjectScanner(root).scan();

    let deployConfig: DeployConfig = {};
    try {
      deployConfig = parseDeployConfig(
        JSON.parse(await readFile(join(root, "deploy.config.json"), "utf8"))
      );
    } catch {
      // defaults
    }

    const checks = await runReadinessChecks(profile, vault, deployConfig);
    return { checks, score: scoreReadiness(checks) };
  }

  async postgresProvision(opts: {
    provider: "neon" | "supabase";
    region?: string;
    name?: string;
    applySchema?: boolean;
  }) {
    const root = this.requireProject();
    const vault = this.requireVault();
    const profile = await new ProjectScanner(root).scan();

    let deployConfig: DeployConfig = {};
    try {
      deployConfig = parseDeployConfig(
        JSON.parse(await readFile(join(root, "deploy.config.json"), "utf8"))
      );
    } catch {
      // defaults
    }

    return provisionPostgres(root, vault, deployConfig, {
      projectName: opts.name ?? profile.name,
      provider: opts.provider,
      region: opts.region,
      applySchema: opts.applySchema !== false,
    });
  }

  async postgresStatus(): Promise<{
    manifest: PostgresManifest | null;
    connected: boolean;
    message: string;
  }> {
    const root = this.requireProject();
    const vault = this.requireVault();
    return getPostgresProvisionStatus(root, vault);
  }

  async diagnose(): Promise<StripeDiagnosticReport> {
    const root = this.requireProject();
    const profile = await new ProjectScanner(root).scan();
    const vault = this.vault;
    return runStripeDiagnostics(profile, vault);
  }

  async fix(opts: { issueIds?: string[]; action?: StripeFixAction; force?: boolean }): Promise<{
    repairs: StripeRepairResult[];
    report: StripeDiagnosticReport;
  }> {
    const root = this.requireProject();
    const vault = this.requireVault();
    const profile = await new ProjectScanner(root).scan();

    let repairs: StripeRepairResult[];
    if (opts.action) {
      repairs = [await runStripeRepair(profile, vault, opts.action)];
    } else {
      repairs = await runAutoFix(profile, vault, {
        issueIds: opts.issueIds,
        force: opts.force,
      });
    }

    const report = await runStripeDiagnostics(profile, vault);
    return { repairs, report };
  }
}
