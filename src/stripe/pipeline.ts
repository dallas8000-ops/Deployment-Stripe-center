import type { ProjectProfile, StripeAutomationConfig, StripeAutomationResult } from "../types.js";
import type { SecretVault } from "../security/vault.js";
import { StripeApiAutomation } from "./api-automation.js";
import { StripeCodeGenerator } from "./code-generator.js";
import { parseStripeConfig, resolveAutomationUrls } from "./config-schema.js";
import { DEFAULT_SAAS_TIERS } from "./default-tiers.js";
import { syncVaultToEnv } from "./env-sync.js";
import { verifyApiKeys } from "./stripe-client.js";
import { writeProjectFiles, type WriteResult } from "../utils/file-writer.js";
import { emitEvent, type PipelineEventHandler } from "./pipeline-events.js";
import { runReadinessChecks, scoreReadiness } from "../deploy/readiness.js";

export interface PipelineOptions {
  provision?: boolean;
  generate?: boolean;
  syncEnv?: boolean;
  force?: boolean;
  config?: StripeAutomationConfig;
  appUrl?: string;
  onEvent?: PipelineEventHandler;
  /** Include readiness score on run.completed (full setup UX). */
  includeReadiness?: boolean;
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
  const onEvent = opts.onEvent;

  emitEvent(onEvent, { step: "run.started", status: "running", message: "Starting full setup…" });

  emitEvent(onEvent, { step: "verify.keys", status: "running", message: "Verifying API keys…" });
  const verification = await verifyApiKeys(vault);
  if (!verification.secretKey.valid) {
    emitEvent(onEvent, {
      step: "verify.keys",
      status: "failed",
      message: verification.secretKey.message,
    });
    throw new Error(verification.secretKey.message);
  }
  const mode = verification.secretKey.mode === "live" ? "live mode" : "test mode";
  emitEvent(onEvent, {
    step: "verify.keys",
    status: "ok",
    message: `API keys verified (${mode})`,
  });

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
    result.provision = await automation.run(config, { onEvent });
  }

  if (opts.generate !== false) {
    emitEvent(onEvent, { step: "generate.code", status: "running", message: "Generating code…" });
    const manifest = await automation.loadManifest();
    const generator = new StripeCodeGenerator(profile);
    const files = generator.generateAll(manifest);
    result.files = await writeProjectFiles(profile.rootPath, files, { force: opts.force });
    for (const f of result.files) {
      if (f.action === "skipped") continue;
      emitEvent(onEvent, {
        step: "generate.file",
        status: "detail",
        message: f.path,
        detail: true,
      });
    }
    const written = result.files.filter((f) => f.action !== "skipped").length;
    emitEvent(onEvent, {
      step: "generate.code",
      status: "ok",
      message: `Code generated (${written} file${written === 1 ? "" : "s"})`,
    });
  }

  if (opts.syncEnv) {
    emitEvent(onEvent, { step: "sync.env", status: "running", message: "Syncing .env.local…" });
    await syncVaultToEnv(profile.rootPath, vault);
    emitEvent(onEvent, { step: "sync.env", status: "ok", message: "Environment synced" });
  }

  let score: number | undefined;
  if (opts.includeReadiness) {
    emitEvent(onEvent, { step: "readiness", status: "running", message: "Running readiness checks…" });
    const checks = await runReadinessChecks(profile, vault, {});
    score = scoreReadiness(checks);
    emitEvent(onEvent, {
      step: "readiness",
      status: "ok",
      message: `Readiness score: ${score}/100`,
    });
  }

  emitEvent(onEvent, {
    step: "run.completed",
    status: "ok",
    message: score !== undefined ? `Done — Readiness Score: ${score}/100` : "Done — setup complete",
    score,
  });

  return result;
}

export function loadConfigFromJson(raw: unknown, appUrl?: string): StripeAutomationConfig {
  const config = parseStripeConfig(raw);
  return { ...config, appUrl: config.appUrl ?? appUrl };
}
