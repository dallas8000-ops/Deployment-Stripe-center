import type { ProjectProfile, StripeAutomationConfig, StripeAutomationResult } from "../types.js";
import type { SecretVault } from "../security/vault.js";
import { StripeApiAutomation } from "./api-automation.js";
import { StripeCodeGenerator } from "./code-generator.js";
import { parseStripeConfig, resolveAutomationUrls } from "./config-schema.js";
import { DEFAULT_SAAS_TIERS } from "./default-tiers.js";
import { syncVaultToEnv } from "./env-sync.js";
import { verifyApiKeys } from "./stripe-client.js";
import { writeProjectFiles, type WriteResult } from "../utils/file-writer.js";

export interface PipelineOptions {
  provision?: boolean;
  generate?: boolean;
  syncEnv?: boolean;
  force?: boolean;
  config?: StripeAutomationConfig;
  appUrl?: string;
}

export interface PipelineResult {
  profile: ProjectProfile;
  verification: Awaited<ReturnType<typeof verifyApiKeys>>;
  provision?: StripeAutomationResult;
  files?: WriteResult[];
}

export async function runPipeline(
  profile: ProjectProfile,
  vault: SecretVault,
  opts: PipelineOptions
): Promise<PipelineResult> {
  const verification = await verifyApiKeys(vault);
  if (!verification.secretKey.valid) {
    throw new Error(verification.secretKey.message);
  }

  const automation = new StripeApiAutomation(profile.rootPath, vault);
  let config = opts.config ?? {};

  if (!config.tiers && !config.productName) {
    config = {
      ...config,
      tiers: DEFAULT_SAAS_TIERS,
    };
  }

  config = resolveAutomationUrls(config, profile, opts.appUrl ?? "http://localhost:3000");

  const result: PipelineResult = { profile, verification };

  if (opts.provision !== false) {
    result.provision = await automation.run(config);
  }

  if (opts.generate !== false) {
    const manifest = await automation.loadManifest();
    const generator = new StripeCodeGenerator(profile);
    const files = generator.generateAll(manifest);
    result.files = await writeProjectFiles(profile.rootPath, files, { force: opts.force });
  }

  if (opts.syncEnv) {
    await syncVaultToEnv(profile.rootPath, vault);
  }

  return result;
}

export function loadConfigFromJson(raw: unknown, appUrl?: string): StripeAutomationConfig {
  const config = parseStripeConfig(raw);
  return { ...config, appUrl: config.appUrl ?? appUrl };
}
