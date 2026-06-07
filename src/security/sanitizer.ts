import type { DetectedSecret, ProjectProfile, SanitizedContext, StripeSetupPlan } from "../types.js";

const SECRET_PATTERNS: { pattern: RegExp; label: string }[] = [
  { pattern: /sk_(live|test)_[A-Za-z0-9]{16,}/g, label: "STRIPE_SECRET_KEY" },
  { pattern: /pk_(live|test)_[A-Za-z0-9]{16,}/g, label: "STRIPE_PUBLISHABLE_KEY" },
  { pattern: /whsec_[A-Za-z0-9]{16,}/g, label: "STRIPE_WEBHOOK_SECRET" },
  { pattern: /rk_(live|test)_[A-Za-z0-9]{16,}/g, label: "STRIPE_RESTRICTED_KEY" },
  {
    // Assignment-style secrets only (avoids STRIPE_SECRET_KEY env refs and code identifiers)
    pattern: /(?:^|[\s;])(?:api[_-]?key|password|passwd|token|credential)\s*=\s*['"]?([a-zA-Z0-9+/=_-]{12,})/gim,
    label: "GENERIC_SECRET",
  },
  { pattern: /Bearer\s+[A-Za-z0-9._-]{20,}/g, label: "BEARER_TOKEN" },
];

/** Skip doc placeholders like sk_test_... or incomplete example values */
function isPlaceholderSecret(match: string): boolean {
  if (match.includes("...") || match.includes("[REDACTED")) return true;
  if (/^(sk|pk|rk)_(live|test)_$/i.test(match)) return true;
  if (/^whsec_$/i.test(match)) return true;
  if (/=sk_live_$/i.test(match) || /=pk_live_$/i.test(match)) return true;
  const codeTokens = ["undefined", "string", "boolean", "number", "value", "null"];
  if (codeTokens.some((t) => match.toLowerCase().endsWith(t))) return true;
  return false;
}

export function redactSecrets(text: string): { sanitized: string; found: DetectedSecret[] } {
  const found: DetectedSecret[] = [];
  let sanitized = text;

  for (const { pattern, label } of SECRET_PATTERNS) {
    sanitized = sanitized.replace(pattern, (match) => {
      if (isPlaceholderSecret(match)) return match;
      const placeholder = `[REDACTED:${label}]`;
      found.push({
        key: label,
        file: "",
        placeholder,
      });
      return placeholder;
    });
  }

  return { sanitized, found };
}

export function sanitizeFileContent(content: string, filePath: string): string {
  let result = content;
  for (const { pattern, label } of SECRET_PATTERNS) {
    result = result.replace(pattern, `[REDACTED:${label}@${filePath}]`);
  }
  return result;
}

export function buildSanitizedContext(
  profile: ProjectProfile,
  plan: StripeSetupPlan
): SanitizedContext {
  const { detectedSecrets, ...safeProfile } = profile;

  const promptContext = [
    `# Project Analysis (sanitized — no secrets)`,
    ``,
    `Project: ${profile.name}`,
    `Framework: ${profile.framework}`,
    `Language: ${profile.language}`,
    `Runtime: ${profile.serverRuntime}`,
    `Existing Stripe code: ${profile.existingStripeCode}`,
    ``,
    `Dependencies: ${profile.dependencies.slice(0, 20).join(", ") || "none"}`,
    `Env files found: ${profile.envFiles.join(", ") || "none"}`,
    `Secret keys detected (redacted): ${detectedSecrets.map((s) => s.key).join(", ") || "none"}`,
    ``,
    `Suggested Stripe features: ${profile.suggestedFeatures.join(", ")}`,
    ``,
    `Recommendations:`,
    ...profile.recommendations.map((r) => `- ${r}`),
    ``,
    `Setup plan:`,
    `- Features: ${plan.features.join(", ")}`,
    `- Packages: ${plan.packagesToInstall.join(", ")}`,
    `- Env vars needed: ${plan.envVars.map((v) => v.key).join(", ")}`,
    `- Files to create: ${plan.filesToCreate.map((f) => f.path).join(", ")}`,
  ].join("\n");

  return {
    profile: {
      ...safeProfile,
      secretKeys: detectedSecrets.map((s) => s.key),
      secretCount: detectedSecrets.length,
    },
    plan,
    promptContext,
  };
}

/** Guard: reject any string that still contains likely secrets before AI submission */
export function assertSafeForAI(text: string): void {
  for (const { pattern } of SECRET_PATTERNS) {
    const test = new RegExp(pattern.source, pattern.flags.replace("g", ""));
    if (test.test(text)) {
      throw new Error(
        "SECURITY: Attempted to send unsanitized content to AI. Aborting."
      );
    }
  }
}
