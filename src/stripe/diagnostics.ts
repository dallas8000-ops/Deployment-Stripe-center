import { readFile, access } from "node:fs/promises";
import { join } from "node:path";
import type { ProjectProfile, StripeDiagnosticReport, StripeIssue } from "../types.js";
import type { SecretVault } from "../security/vault.js";
import { verifyApiKeys, getStripeClient } from "./stripe-client.js";
import { StripeApiAutomation } from "./api-automation.js";
import { StripeCodeGenerator } from "./code-generator.js";
import { findEnvFile } from "./env-sync.js";
import {
  getFrameworkCapabilities,
  supportsFileDiagnostics,
} from "./framework-profiles.js";

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

async function envHasKey(root: string, envFile: string, key: string): Promise<boolean> {
  try {
    const content = await readFile(join(root, envFile), "utf8");
    return new RegExp(`^${key}=.+`, "m").test(content);
  } catch {
    return false;
  }
}

function scoreIssues(issues: StripeIssue[]): number {
  if (issues.length === 0) return 100;
  const weights = { error: 0, warning: 0.5, info: 0.85 };
  const total = issues.reduce((sum, i) => sum + weights[i.severity], 0);
  return Math.round((total / issues.length) * 100);
}

function push(issues: StripeIssue[], issue: StripeIssue): void {
  if (!issues.some((i) => i.id === issue.id)) issues.push(issue);
}

export async function runStripeDiagnostics(
  profile: ProjectProfile,
  vault?: SecretVault | null
): Promise<StripeDiagnosticReport> {
  const root = profile.rootPath;
  const issues: StripeIssue[] = [];
  const cap = getFrameworkCapabilities(profile.framework);
  const generator = new StripeCodeGenerator(profile);
  const expectedFiles = generator.getPlannedPaths();
  const checkFiles = supportsFileDiagnostics(profile);

  // ── Security ──
  if (profile.detectedSecrets.length > 0) {
    push(issues, {
      id: "secrets-in-files",
      category: "security",
      severity: "error",
      title: "Secrets exposed in project files",
      message: `${profile.detectedSecrets.length} API key(s) found in source or env files`,
      fixHint: "Import to vault and remove from tracked files",
      autoFixable: Boolean(vault),
      fixAction: vault ? "import-env" : undefined,
    });
  }

  const gitignore = await readGitignore(root);
  if (!gitignore.includes(".env")) {
    push(issues, {
      id: "gitignore-env",
      category: "security",
      severity: "error",
      title: ".env files not gitignored",
      message: ".env and .env.local may be committed to git",
      fixHint: "Add .env* patterns to .gitignore",
      autoFixable: true,
      fixAction: "fix-gitignore",
    });
  }

  // ── Packages ──
  const hasStripe = profile.dependencies.includes("stripe") || profile.devDependencies.includes("stripe");
  if (!hasStripe && profile.existingStripeCode) {
    push(issues, {
      id: "missing-stripe-package",
      category: "packages",
      severity: "error",
      title: "stripe npm package missing",
      message: "Stripe code detected but `stripe` is not in package.json",
      fixHint: "Run: npm install stripe",
      autoFixable: false,
    });
  }

  if (
    profile.suggestedFeatures.includes("checkout") &&
    !profile.dependencies.includes("@stripe/stripe-js") &&
    profile.framework === "nextjs"
  ) {
    push(issues, {
      id: "missing-stripe-js",
      category: "packages",
      severity: "warning",
      title: "@stripe/stripe-js not installed",
      message: "Checkout UI typically needs @stripe/stripe-js on the client",
      fixHint: "Run: npm install @stripe/stripe-js @stripe/react-stripe-js",
      autoFixable: false,
    });
  }

  // ── Config ──
  const hasStripeConfig = await fileExists(join(root, "stripe.config.json"));
  if (!hasStripeConfig) {
    push(issues, {
      id: "missing-stripe-config",
      category: "config",
      severity: "warning",
      title: "stripe.config.json missing",
      message: "No pricing/webhook configuration file found",
      fixHint: "Create from stripe.config.example.json",
      autoFixable: true,
      fixAction: "create-stripe-config",
    });
  }

  // ── Files ──
  if (cap.codegen === "none") {
    push(issues, {
      id: "manual-framework-setup",
      category: "files",
      severity: "info",
      title: `${cap.displayName} — manual integration`,
      message: cap.summary,
      fixHint: "Run generate-files for setup docs, or follow Stripe SDK guides",
      autoFixable: Boolean(vault),
      fixAction: vault ? "generate-files" : undefined,
    });
  }

  const missingFiles: string[] = [];
  if (checkFiles) {
    for (const f of expectedFiles) {
      if (f === ".env.example" || f.startsWith("docs/")) continue;
      if (!(await fileExists(join(root, f)))) missingFiles.push(f);
    }
  }

  if (missingFiles.length > 0 && profile.suggestedFeatures.length > 0 && checkFiles) {
    const critical = missingFiles.filter((f) =>
      f.includes("webhook") || f.includes("stripe.ts") || f.includes("stripe/views") || f.includes("checkout")
    );
    push(issues, {
      id: "missing-integration-files",
      category: "files",
      severity: critical.length > 0 ? "error" : "warning",
      title: "Missing Stripe integration files",
      message: `${missingFiles.length} expected file(s) not found (e.g. ${missingFiles.slice(0, 2).join(", ")})`,
      fixHint: "Generate boilerplate integration code",
      autoFixable: Boolean(vault),
      fixAction: vault ? "generate-files" : undefined,
    });
  }

  // Webhook handler quality
  const webhookPaths = checkFiles ? expectedFiles.filter((f) => f.includes("webhook")) : [];
  for (const wp of webhookPaths) {
    const full = join(root, wp);
    if (await fileExists(full)) {
      const content = await readFile(full, "utf8");
      if (!content.includes("constructEvent") && !content.includes("construct_event")) {
        push(issues, {
          id: "webhook-no-signature-verify",
          category: "webhooks",
          severity: "error",
          title: "Webhook missing signature verification",
          message: `${wp} does not use stripe.webhooks.constructEvent`,
          fixHint: "Regenerate webhook handler with secure verification",
          autoFixable: Boolean(vault),
          fixAction: vault ? "generate-files" : undefined,
        });
      }
    }
  }

  // ── Credentials (vault) ──
  if (!vault) {
    push(issues, {
      id: "vault-locked",
      category: "credentials",
      severity: "warning",
      title: "Vault not unlocked",
      message: "Cannot verify API keys — unlock vault for full diagnosis",
      fixHint: "Unlock vault in the app or CLI",
      autoFixable: false,
    });
  } else {
    const vaultKeys = await vault.listKeys();
    const required = ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY"];
    for (const key of required) {
      if (!vaultKeys.includes(key)) {
        push(issues, {
          id: `vault-missing-${key.toLowerCase()}`,
          category: "credentials",
          severity: "error",
          title: `${key} not in vault`,
          message: `Required Stripe credential missing from encrypted vault`,
          fixHint: "Import from .env.local or vault set",
          autoFixable: true,
          fixAction: "import-env",
        });
      }
    }

    if (
      profile.framework === "nextjs" &&
      vaultKeys.includes("STRIPE_PUBLISHABLE_KEY") &&
      !vaultKeys.includes("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY")
    ) {
      push(issues, {
        id: "missing-public-env-key",
        category: "credentials",
        severity: "warning",
        title: "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY missing",
        message: "Client-side checkout needs the public key in NEXT_PUBLIC_* env var",
        fixHint: "Sync publishable key to NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
        autoFixable: true,
        fixAction: "sync-public-key",
      });
    }

    const verification = await verifyApiKeys(vault);
    if (!verification.secretKey.valid) {
      push(issues, {
        id: "invalid-secret-key",
        category: "credentials",
        severity: "error",
        title: "Stripe secret key invalid",
        message: verification.secretKey.message,
        fixHint: "Update STRIPE_SECRET_KEY in vault with a valid sk_test_ or sk_live_ key",
        autoFixable: false,
      });
    }

    if (!verification.publishableKey.valid && vaultKeys.includes("STRIPE_PUBLISHABLE_KEY")) {
      push(issues, {
        id: "invalid-publishable-key",
        category: "credentials",
        severity: "error",
        title: "Stripe publishable key invalid",
        message: verification.publishableKey.message,
        fixHint: "Ensure pk_test_/pk_live_ matches secret key mode",
        autoFixable: false,
      });
    }

    if (
      verification.secretKey.valid &&
      verification.publishableKey.valid &&
      verification.secretKey.mode !== verification.publishableKey.mode
    ) {
      push(issues, {
        id: "key-mode-mismatch",
        category: "credentials",
        severity: "error",
        title: "Test/live key mode mismatch",
        message: `Secret is ${verification.secretKey.mode}, publishable is ${verification.publishableKey.mode}`,
        fixHint: "Use matching test or live key pairs",
        autoFixable: false,
      });
    }

    const envFile = (await findEnvFile(root)) ?? ".env.local";
    const envExists = await fileExists(join(root, envFile));
    if (envExists && vaultKeys.some((k) => k.startsWith("STRIPE_"))) {
      const secretInEnv = await envHasKey(root, envFile, "STRIPE_SECRET_KEY");
      const secretInVault = vaultKeys.includes("STRIPE_SECRET_KEY");
      if (secretInVault && !secretInEnv) {
        push(issues, {
          id: "env-out-of-sync",
          category: "credentials",
          severity: "warning",
          title: ".env.local out of sync with vault",
          message: `Keys in vault but missing from ${envFile}`,
          fixHint: "Sync vault secrets to .env.local",
          autoFixable: true,
          fixAction: "sync-env",
        });
      }
    }

    if (!vaultKeys.includes("STRIPE_WEBHOOK_SECRET")) {
      push(issues, {
        id: "missing-webhook-secret",
        category: "webhooks",
        severity: "warning",
        title: "STRIPE_WEBHOOK_SECRET not configured",
        message: "Webhook handler cannot verify Stripe signatures without whsec_",
        fixHint: "Provision webhook via Stripe API or stripe listen",
        autoFixable: true,
        fixAction: "provision-stripe",
      });
    }

    // ── Catalog & webhooks (API) ──
    if (verification.secretKey.valid) {
      const automation = new StripeApiAutomation(root, vault);
      const manifest = await automation.loadManifest();

      if (!manifest || manifest.prices.length === 0) {
        push(issues, {
          id: "no-catalog-manifest",
          category: "catalog",
          severity: "warning",
          title: "No Stripe product catalog",
          message: "No prices provisioned — checkout may fail",
          fixHint: "Run provision to create products and prices",
          autoFixable: true,
          fixAction: "provision-stripe",
        });
      } else {
        try {
          const stripe = await getStripeClient(vault);
          for (const price of manifest.prices) {
            try {
              const p = await stripe.prices.retrieve(price.id);
              if (!p.active) {
                push(issues, {
                  id: `price-inactive-${price.id}`,
                  category: "catalog",
                  severity: "error",
                  title: `Price inactive: ${price.tier}`,
                  message: `Price ${price.id} exists but is archived in Stripe`,
                  fixHint: "Re-run provision or activate in Stripe Dashboard",
                  autoFixable: true,
                  fixAction: "provision-stripe",
                });
              }
            } catch {
              push(issues, {
                id: `price-missing-${price.id}`,
                category: "catalog",
                severity: "error",
                title: `Price not found: ${price.tier}`,
                message: `Manifest references ${price.id} but it does not exist in Stripe`,
                fixHint: "Re-provision catalog from stripe.config.json",
                autoFixable: true,
                fixAction: "provision-stripe",
              });
            }
          }
        } catch {
          // API errors handled by key verification
        }
      }

      if (manifest?.webhookEndpoint) {
        try {
          const stripe = await getStripeClient(vault);
          const endpoint = await stripe.webhookEndpoints.retrieve(manifest.webhookEndpoint.id);
          if (endpoint.status !== "enabled") {
            push(issues, {
              id: "webhook-disabled",
              category: "webhooks",
              severity: "error",
              title: "Webhook endpoint disabled",
              message: `Endpoint ${manifest.webhookEndpoint.url} is disabled in Stripe`,
              fixHint: "Re-provision webhook or enable in Dashboard",
              autoFixable: true,
              fixAction: "provision-stripe",
            });
          }
        } catch {
          push(issues, {
            id: "webhook-endpoint-missing",
            category: "webhooks",
            severity: "error",
            title: "Registered webhook not found",
            message: "Manifest webhook ID no longer exists in Stripe account",
            fixHint: "Re-register webhook endpoint",
            autoFixable: true,
            fixAction: "provision-stripe",
          });
        }
      } else if (profile.suggestedFeatures.includes("webhooks")) {
        push(issues, {
          id: "webhook-not-registered",
          category: "webhooks",
          severity: "warning",
          title: "No webhook endpoint registered",
          message: "Stripe cannot deliver events without a registered endpoint",
          fixHint: "Provision webhook with your app URL",
          autoFixable: true,
          fixAction: "provision-stripe",
        });
      }
    }
  }

  const healthScore = scoreIssues(issues);
  const errors = issues.filter((i) => i.severity === "error").length;
  const warnings = issues.filter((i) => i.severity === "warning").length;
  const fixable = issues.filter((i) => i.autoFixable).length;

  let summary: string;
  if (issues.length === 0) {
    summary = "Stripe setup looks healthy — no issues detected.";
  } else {
    summary = `Found ${issues.length} issue(s): ${errors} error(s), ${warnings} warning(s). ${fixable} auto-fixable.`;
  }

  return {
    scannedAt: new Date().toISOString(),
    projectName: profile.name,
    healthScore,
    issues,
    summary,
  };
}
