import { writeFile, readFile, mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";
import { access } from "node:fs/promises";
import type { ProjectProfile, StripeFeature, StripeSetupPlan } from "../types.js";
import { SecretVault } from "../security/vault.js";
import { verifyApiKeys } from "./stripe-client.js";
import { StripeCodeGenerator } from "./code-generator.js";
import { StripeApiAutomation } from "./api-automation.js";

export class StripeSetupEngine {
  constructor(
    private readonly profile: ProjectProfile,
    private readonly vault: SecretVault
  ) {}

  buildPlan(features?: StripeFeature[]): StripeSetupPlan {
    const selected = features ?? this.profile.suggestedFeatures;
    const isNode = ["typescript", "javascript"].includes(this.profile.language);
    const isNext = this.profile.framework === "nextjs";

    const envVars = [
      {
        key: "STRIPE_SECRET_KEY",
        description: "Stripe secret API key (sk_test_... or sk_live_...)",
        required: true,
      },
      {
        key: "STRIPE_PUBLISHABLE_KEY",
        description: "Stripe publishable key for client-side (pk_test_... or pk_live_...)",
        required: true,
      },
    ];

    if (selected.includes("webhooks")) {
      envVars.push({
        key: "STRIPE_WEBHOOK_SECRET",
        description: "Webhook signing secret (whsec_...)",
        required: true,
      });
    }

    const packagesToInstall = isNode ? ["stripe"] : [];
    if (selected.includes("checkout") && isNode) {
      packagesToInstall.push("@stripe/stripe-js");
      if (this.profile.framework === "react" || isNext) {
        packagesToInstall.push("@stripe/react-stripe-js");
      }
    }

    const filesToCreate: StripeSetupPlan["filesToCreate"] = [];
    const filesToModify: StripeSetupPlan["filesToModify"] = [];
    let webhookPath: string | undefined;

    if (isNext && selected.includes("webhooks")) {
      webhookPath = "app/api/stripe/webhook/route.ts";
      filesToCreate.push({
        path: webhookPath,
        purpose: "Stripe webhook handler with signature verification",
      });
    } else if (
      (this.profile.framework === "express" || this.profile.framework === "fastify") &&
      selected.includes("webhooks")
    ) {
      webhookPath = "src/routes/stripe-webhook.ts";
      filesToCreate.push({
        path: webhookPath,
        purpose: "Express webhook endpoint with raw body parsing",
      });
    }

    if (isNext && selected.includes("checkout")) {
      filesToCreate.push({
        path: "app/api/stripe/checkout/route.ts",
        purpose: "Create Stripe Checkout sessions",
      });
      filesToCreate.push({
        path: "app/pricing/page.tsx",
        purpose: "Pricing page with checkout buttons",
      });
      filesToCreate.push({
        path: "components/CheckoutButton.tsx",
        purpose: "Client-side checkout button component",
      });
    }

    if (isNext && (selected.includes("billing-portal") || selected.includes("subscriptions"))) {
      filesToCreate.push({
        path: "app/api/stripe/portal/route.ts",
        purpose: "Stripe Customer Billing Portal session",
      });
    }

    if (selected.includes("subscriptions")) {
      filesToCreate.push({
        path: "lib/stripe-config.ts",
        purpose: "Price ID mapping from Stripe manifest",
      });
    }

    if (!this.profile.hasEnvFile) {
      filesToCreate.push({
        path: ".env.example",
        purpose: "Template env file with placeholder keys (safe to commit)",
      });
    }

    filesToCreate.push({
      path: "lib/stripe.ts",
      purpose: "Centralized Stripe client initialization",
    });

    if (!this.profile.existingStripeCode) {
      filesToModify.push({
        path: isNext ? "app/layout.tsx" : "src/App.tsx",
        purpose: "Wrap app with Stripe provider if checkout enabled",
      });
    }

    const notes = [
      "All generated code uses process.env references — actual keys stay in vault.",
      "Run stripe listen --forward-to <webhook-url> for local webhook testing.",
      "Use test mode keys until production launch.",
    ];

    return {
      features: selected,
      envVars,
      packagesToInstall: [...new Set(packagesToInstall)],
      filesToCreate,
      filesToModify,
      webhookPath,
      notes,
    };
  }

  async validateConnection(): Promise<{ ok: boolean; message: string }> {
    const verified = await verifyApiKeys(this.vault);
    if (!verified.secretKey.valid) {
      return { ok: false, message: verified.secretKey.message };
    }
    const parts = [verified.secretKey.message];
    if (verified.publishableKey.valid) {
      parts.push(verified.publishableKey.message);
    }
    if (verified.accountName) {
      parts.push(`Account: ${verified.accountName}`);
    }
    return { ok: true, message: parts.join(" | ") };
  }

  async applyPlan(plan: StripeSetupPlan): Promise<string[]> {
    const automation = new StripeApiAutomation(this.profile.rootPath, this.vault);
    const manifest = await automation.loadManifest();
    const generator = new StripeCodeGenerator(this.profile);
    const generated = generator.generateAll(manifest);

    const created: string[] = [];
    const pathsToWrite = new Set(plan.filesToCreate.map((f) => f.path));

    for (const [relativePath, content] of Object.entries(generated)) {
      if (!pathsToWrite.has(relativePath) && !relativePath.startsWith("lib/")) continue;

      const fullPath = join(this.profile.rootPath, relativePath);
      if (await this.exists(fullPath)) continue;

      await mkdir(dirname(fullPath), { recursive: true });
      await writeFile(fullPath, content, "utf8");
      created.push(relativePath);
    }

    for (const file of plan.filesToCreate) {
      if (created.includes(file.path)) continue;

      const fullPath = join(this.profile.rootPath, file.path);
      if (await this.exists(fullPath)) continue;

      await mkdir(dirname(fullPath), { recursive: true });
      const content = generated[file.path] ?? this.generateFileContent(file.path, plan);
      await writeFile(fullPath, content, "utf8");
      created.push(file.path);
    }

    return created;
  }

  async writeEnvExample(plan: StripeSetupPlan): Promise<void> {
    const lines = [
      "# Stripe configuration — copy to .env.local and fill in values",
      "# NEVER commit real keys. Use: stripe-installer vault set <KEY> <VALUE>",
      "",
      ...plan.envVars.map((v) => `${v.key}=`),
      "",
    ];
    const path = join(this.profile.rootPath, ".env.example");
    if (!(await this.exists(path))) {
      await writeFile(path, lines.join("\n"), "utf8");
    }
  }

  private async exists(path: string): Promise<boolean> {
    try {
      await access(path);
      return true;
    } catch {
      return false;
    }
  }

  private generateFileContent(relativePath: string, plan: StripeSetupPlan): string {
    if (relativePath === "lib/stripe.ts") {
      return `import Stripe from "stripe";

if (!process.env.STRIPE_SECRET_KEY) {
  throw new Error("STRIPE_SECRET_KEY is not set");
}

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY, {
  apiVersion: "2025-02-24.acacia",
  typescript: true,
});
`;
    }

    if (relativePath.endsWith("webhook/route.ts")) {
      return `import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import Stripe from "stripe";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const signature = req.headers.get("stripe-signature");

  if (!signature || !process.env.STRIPE_WEBHOOK_SECRET) {
    return NextResponse.json({ error: "Missing signature or webhook secret" }, { status: 400 });
  }

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(
      body,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Webhook verification failed";
    return NextResponse.json({ error: message }, { status: 400 });
  }

  switch (event.type) {
    case "checkout.session.completed":
      // Handle successful checkout
      break;
    case "customer.subscription.updated":
      // Handle subscription changes
      break;
    default:
      console.log(\`Unhandled event type: \${event.type}\`);
  }

  return NextResponse.json({ received: true });
}
`;
    }

    if (relativePath.endsWith("checkout/route.ts")) {
      return `import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";

export async function POST(req: NextRequest) {
  const { priceId, successUrl, cancelUrl } = await req.json();

  const session = await stripe.checkout.sessions.create({
    mode: "payment",
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: successUrl ?? \`\${process.env.NEXT_PUBLIC_APP_URL}/success\`,
    cancel_url: cancelUrl ?? \`\${process.env.NEXT_PUBLIC_APP_URL}/cancel\`,
  });

  return NextResponse.json({ url: session.url });
}
`;
    }

    if (relativePath === ".env.example") {
      return (
        plan.envVars.map((v) => `${v.key}=`).join("\n") +
        "\nNEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=\n"
      );
    }

    return `// Generated by stripe-installer for: ${relativePath}\n`;
  }

  async injectSecretsToEnvLocal(): Promise<void> {
    const envPath = join(this.profile.rootPath, ".env.local");
    let existing = "";
    try {
      existing = await readFile(envPath, "utf8");
    } catch {
      // new file
    }

    const keys = await this.vault.listKeys();
    const lines = existing.split("\n").filter(Boolean);
    const existingKeys = new Set(lines.map((l) => l.split("=")[0]));

    for (const key of keys) {
      if (existingKeys.has(key)) continue;
      const value = await this.vault.get(key);
      if (value) lines.push(`${key}=${value}`);
    }

    if (lines.length > 0) {
      await writeFile(envPath, lines.join("\n") + "\n", "utf8");
    }
  }
}
