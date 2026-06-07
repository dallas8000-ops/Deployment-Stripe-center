import type { ProjectProfile, SanitizedContext, StripeSetupPlan } from "../types.js";
import { buildSanitizedContext, assertSafeForAI } from "../security/sanitizer.js";
import { StripeSetupEngine } from "../stripe/setup-engine.js";
import { SecretVault } from "../security/vault.js";

export interface AIProvider {
  name: string;
  complete(prompt: string): Promise<string>;
}

/**
 * Orchestrates AI-assisted setup while enforcing the secrets boundary.
 * Only sanitized context crosses into AI — never vault contents.
 */
export class AIOrchestrator {
  constructor(
    private readonly profile: ProjectProfile,
    private readonly vault: SecretVault,
    private readonly provider?: AIProvider
  ) {}

  prepareContext(features?: string[]): SanitizedContext {
    const engine = new StripeSetupEngine(this.profile, this.vault);
    const plan = engine.buildPlan(
      features as ProjectProfile["suggestedFeatures"] | undefined
    );
    return buildSanitizedContext(this.profile, plan);
  }

  async generateRecommendations(): Promise<string> {
    const context = this.prepareContext();
    assertSafeForAI(context.promptContext);

    if (!this.provider) {
      return this.localRecommendations(context);
    }

    const prompt = this.buildPrompt(context);
    assertSafeForAI(prompt);
    return this.provider.complete(prompt);
  }

  private buildPrompt(context: SanitizedContext): string {
    return [
      "You are a Stripe integration expert. Analyze this SANITIZED project profile",
      "and provide specific, actionable setup guidance.",
      "",
      "RULES:",
      "- Never ask for or reference actual API keys",
      "- Use environment variable names only (e.g. STRIPE_SECRET_KEY)",
      "- Tailor advice to the detected framework and language",
      "- Be concise and production-focused",
      "",
      context.promptContext,
      "",
      "Provide:",
      "1. Priority setup steps (ordered)",
      "2. Security considerations for this stack",
      "3. Recommended Stripe features for this project type",
      "4. Testing checklist",
    ].join("\n");
  }

  private localRecommendations(context: SanitizedContext): string {
    const { profile, plan } = context;

    return [
      `# Stripe Setup Recommendations for ${profile.name}`,
      ``,
      `## Detected Stack`,
      `- Framework: ${profile.framework}`,
      `- Language: ${profile.language}`,
      `- Runtime: ${profile.serverRuntime}`,
      ``,
      `## Priority Steps`,
      ...plan.envVars.map(
        (v, i) =>
          `${i + 1}. Configure ${v.key} — ${v.description}${v.required ? " (required)" : ""}`
      ),
      `${plan.envVars.length + 1}. Install packages: ${plan.packagesToInstall.join(", ") || "none"}`,
      ...plan.filesToCreate.map(
        (f, i) =>
          `${plan.envVars.length + 2 + i}. Create ${f.path} — ${f.purpose}`
      ),
      ``,
      `## Security`,
      `- Store keys in the encrypted vault (stripe-installer vault set)`,
      `- Never pass secrets to AI prompts — this session is sanitized`,
      `- Use test keys until production deployment`,
      `- Add .env.local to .gitignore`,
      ``,
      `## Features`,
      plan.features.map((f) => `- ${f}`).join("\n"),
      ``,
      `## Testing Checklist`,
      `- [ ] stripe-installer vault set STRIPE_SECRET_KEY sk_test_...`,
      `- [ ] Run: stripe-installer setup --validate`,
      `- [ ] Test checkout flow with Stripe test card 4242 4242 4242 4242`,
      `- [ ] Forward webhooks: stripe listen --forward-to localhost:3000/api/stripe/webhook`,
      ``,
      `## Notes`,
      ...plan.notes.map((n) => `- ${n}`),
      ``,
      `> Connect an AI provider via OPENAI_API_KEY or ANTHROPIC_API_KEY for deeper analysis.`,
    ].join("\n");
  }
}

const AI_SYSTEM_PROMPT =
  "You are a Stripe integration expert. Never ask for or output real API keys.";

/** Wire to OpenAI or Anthropic when API key is in vault (keys never logged) */
export function createAIProvider(vault: SecretVault): AIProvider | undefined {
  // Caller should use hasAIProvider() first; provider resolves key on first complete()
  let providerName: "anthropic" | "openai" | null = null;

  return {
    name: "vault",
    async complete(prompt: string): Promise<string> {
      assertSafeForAI(prompt);

      if (!providerName) {
        if (await vault.get("ANTHROPIC_API_KEY")) providerName = "anthropic";
        else if (await vault.get("OPENAI_API_KEY")) providerName = "openai";
        else {
          throw new Error(
            "No AI key in vault. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
          );
        }
      }

      if (providerName === "anthropic") {
        const key = await vault.get("ANTHROPIC_API_KEY");
        if (!key) throw new Error("ANTHROPIC_API_KEY not in vault");
        return completeWithAnthropic(key, prompt);
      }

      const key = await vault.get("OPENAI_API_KEY");
      if (!key) throw new Error("OPENAI_API_KEY not in vault");
      return completeWithOpenAI(key, prompt);
    },
  };
}

export async function hasAIProvider(vault: SecretVault): Promise<boolean> {
  return Boolean((await vault.get("ANTHROPIC_API_KEY")) || (await vault.get("OPENAI_API_KEY")));
}

async function completeWithOpenAI(apiKey: string, prompt: string): Promise<string> {
  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      messages: [
        { role: "system", content: AI_SYSTEM_PROMPT },
        { role: "user", content: prompt },
      ],
      temperature: 0.3,
    }),
  });

  if (!response.ok) {
    throw new Error(`OpenAI request failed: ${response.statusText}`);
  }

  const data = (await response.json()) as {
    choices: { message: { content: string } }[];
  };
  return data.choices[0]?.message?.content ?? "No response";
}

async function completeWithAnthropic(apiKey: string, prompt: string): Promise<string> {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 2048,
      system: AI_SYSTEM_PROMPT,
      messages: [{ role: "user", content: prompt }],
    }),
  });

  if (!response.ok) {
    throw new Error(`Anthropic request failed: ${response.statusText}`);
  }

  const data = (await response.json()) as {
    content: { type: string; text?: string }[];
  };
  return data.content.find((c) => c.type === "text")?.text ?? "No response";
}
