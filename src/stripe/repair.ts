import { readFile, writeFile, copyFile, access } from "node:fs/promises";
import { join } from "node:path";
import type {
  ProjectProfile,
  StripeFixAction,
  StripeIssue,
  StripeRepairResult,
} from "../types.js";
import type { SecretVault } from "../security/vault.js";
import { StripeCodeGenerator } from "./code-generator.js";
import { StripeApiAutomation } from "./api-automation.js";
import { importEnvToVault, syncVaultToEnv } from "./env-sync.js";
import { runStripeDiagnostics } from "./diagnostics.js";
import { parseStripeConfig, resolveAutomationUrls } from "./config-schema.js";
import { DEFAULT_SAAS_TIERS } from "./default-tiers.js";
import { writeProjectFiles } from "../utils/file-writer.js";

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function fixGitignore(root: string): Promise<StripeRepairResult> {
  const path = join(root, ".gitignore");
  let content = "";
  try {
    content = await readFile(path, "utf8");
  } catch {
    content = "";
  }

  const additions = [".env", ".env.local", ".env.*.local", ".stripe-installer/"];
  const lines = content.split("\n");
  const existing = new Set(lines.map((l) => l.trim()).filter(Boolean));
  const added = additions.filter((a) => !existing.has(a) && !content.includes(a));

  if (added.length === 0) {
    return { action: "fix-gitignore", success: true, message: ".gitignore already configured" };
  }

  const block = ["", "# Stripe Installer", ...added].join("\n");
  await writeFile(path, content.trimEnd() + block + "\n", "utf8");
  return {
    action: "fix-gitignore",
    success: true,
    message: `Added ${added.join(", ")} to .gitignore`,
  };
}

async function createStripeConfig(root: string): Promise<StripeRepairResult> {
  const dest = join(root, "stripe.config.json");
  if (await fileExists(dest)) {
    return { action: "create-stripe-config", success: true, message: "stripe.config.json already exists" };
  }

  const example = join(root, "stripe.config.example.json");

  if (await fileExists(example)) {
    await copyFile(example, dest);
  } else if (await fileExists(join(process.cwd(), "stripe.config.example.json"))) {
    await copyFile(join(process.cwd(), "stripe.config.example.json"), dest);
  } else {
    await writeFile(
      dest,
      JSON.stringify(
        {
          appUrl: "http://localhost:3000",
          webhookUrl: "http://localhost:3000/api/stripe/webhook",
          billingPortalReturnUrl: "http://localhost:3000/account",
          tiers: DEFAULT_SAAS_TIERS,
        },
        null,
        2
      ) + "\n",
      "utf8"
    );
  }

  return { action: "create-stripe-config", success: true, message: "Created stripe.config.json" };
}

async function syncPublicKey(vault: SecretVault): Promise<StripeRepairResult> {
  const pk = await vault.get("STRIPE_PUBLISHABLE_KEY");
  if (!pk) {
    return { action: "sync-public-key", success: false, message: "STRIPE_PUBLISHABLE_KEY not in vault" };
  }
  await vault.set("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", pk);
  return { action: "sync-public-key", success: true, message: "Synced NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY" };
}

async function generateMissingFiles(
  profile: ProjectProfile,
  vault: SecretVault,
  force: boolean
): Promise<StripeRepairResult> {
  const automation = new StripeApiAutomation(profile.rootPath, vault);
  const manifest = await automation.loadManifest();
  const generator = new StripeCodeGenerator(profile);
  const allFiles = generator.generateAll(manifest);

  const toWrite: Record<string, string> = {};
  for (const [path, content] of Object.entries(allFiles)) {
    const exists = await fileExists(join(profile.rootPath, path));
    if (!exists || force) toWrite[path] = content;
  }

  if (Object.keys(toWrite).length === 0) {
    return { action: "generate-files", success: true, message: "All integration files already exist" };
  }

  const results = await writeProjectFiles(profile.rootPath, toWrite, { force });
  const created = results.filter((r) => r.action !== "skipped").map((r) => r.path);
  return {
    action: "generate-files",
    success: true,
    message: `Generated ${created.length} file(s)`,
    files: created,
  };
}

async function provisionStripe(profile: ProjectProfile, vault: SecretVault): Promise<StripeRepairResult> {
  const root = profile.rootPath;
  let config = resolveAutomationUrls(
    { tiers: DEFAULT_SAAS_TIERS, appUrl: "http://localhost:3000" },
    profile,
    "http://localhost:3000"
  );

  try {
    const raw = JSON.parse(await readFile(join(root, "stripe.config.json"), "utf8"));
    config = resolveAutomationUrls(parseStripeConfig(raw), profile, config.appUrl ?? "http://localhost:3000");
  } catch {
    // defaults
  }

  const automation = new StripeApiAutomation(root, vault);
  const result = await automation.run(config);
  return {
    action: "provision-stripe",
    success: true,
    message: `Provisioned ${result.prices.length} price(s), webhook ${result.webhookEndpoint ? "registered" : "skipped"}`,
  };
}

export async function runStripeRepair(
  profile: ProjectProfile,
  vault: SecretVault,
  action: StripeFixAction
): Promise<StripeRepairResult> {
  const root = profile.rootPath;

  switch (action) {
    case "import-env": {
      const imported = await importEnvToVault(root, vault);
      if (imported.length === 0) {
        return { action, success: false, message: "No Stripe keys found in .env.local" };
      }
      await syncPublicKey(vault).catch(() => undefined);
      return { action, success: true, message: `Imported ${imported.length} key(s) to vault` };
    }
    case "sync-env": {
      const synced = await syncVaultToEnv(root, vault);
      return {
        action,
        success: true,
        message: synced.length ? `Synced ${synced.length} key(s) to .env.local` : "No Stripe keys to sync",
      };
    }
    case "sync-public-key":
      return syncPublicKey(vault);
    case "generate-files":
      return generateMissingFiles(profile, vault, false);
    case "provision-stripe":
      return provisionStripe(profile, vault);
    case "fix-gitignore":
      return fixGitignore(root);
    case "create-stripe-config":
      return createStripeConfig(root);
    default:
      return { action, success: false, message: `Unknown repair action: ${action}` };
  }
}

export async function runAutoFix(
  profile: ProjectProfile,
  vault: SecretVault,
  opts: { issueIds?: string[]; force?: boolean } = {}
): Promise<StripeRepairResult[]> {
  const report = await runStripeDiagnostics(profile, vault);
  let targets: StripeIssue[];

  if (opts.issueIds?.length) {
    targets = report.issues.filter((i) => opts.issueIds!.includes(i.id) && i.autoFixable && i.fixAction);
  } else {
    targets = report.issues.filter((i) => i.autoFixable && i.fixAction);
  }

  const actions = [...new Set(targets.map((t) => t.fixAction!))];
  const results: StripeRepairResult[] = [];

  for (const action of actions) {
    if (action === "generate-files" && opts.force) {
      results.push(await generateMissingFiles(profile, vault, true));
    } else {
      results.push(await runStripeRepair(profile, vault, action));
    }
  }

  return results;
}
