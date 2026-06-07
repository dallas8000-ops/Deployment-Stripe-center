import type { ProjectProfile, StripeManifest } from "../types.js";
import { getFrameworkCapabilities, libDir } from "./framework-profiles.js";
import { formatAmount, tierKey } from "./tier-format.js";
import {
  djangoPageViews,
  djangoSessionView,
  djangoUrlsWithPages,
  flaskPageRoutes,
  generateUiFiles,
} from "./ui-generators.js";
import {
  generateSessionInfoRoute,
} from "./session-routes.js";
import { generateAuthIntegration } from "./auth-integration.js";

export class StripeCodeGenerator {
  constructor(private readonly profile: ProjectProfile) {}

  generateAll(manifest?: StripeManifest | null): Record<string, string> {
    const files: Record<string, string> = {};
    const cap = getFrameworkCapabilities(this.profile.framework);
    const isNext = this.profile.framework === "nextjs";
    const useAppRouter = this.profile.nextRouter !== "pages";
    const lib = libDir(this.profile);
    const fw = this.profile.framework;

    if (cap.codegen === "none") {
      files["docs/STRIPE-SETUP.md"] = this.manualSetupGuide();
      files[".env.example"] = this.envExample();
      return files;
    }

    if (fw === "django") {
      files["stripe/__init__.py"] = "";
      files["stripe/client.py"] = this.djangoStripeClient();
      files["stripe/views.py"] = this.djangoViews(manifest) + djangoSessionView() + "\n" + djangoPageViews();
      files["stripe/urls.py"] = djangoUrlsWithPages();
      files["docs/STRIPE-DJANGO.md"] = this.djangoSetupGuide();
      files[".env.example"] = this.pythonEnvExample();
      Object.assign(files, generateUiFiles("django", manifest));
      return files;
    }

    if (fw === "flask") {
      files["stripe_routes.py"] = this.flaskBlueprint(manifest);
      files["docs/STRIPE-FLASK.md"] = this.flaskSetupGuide();
      files[".env.example"] = this.pythonEnvExample();
      Object.assign(files, generateUiFiles("flask", manifest));
      return files;
    }

    if (fw === "rails") {
      files["app/controllers/stripe_controller.rb"] = this.railsController(manifest);
      files["docs/STRIPE-RAILS.md"] = this.railsSetupGuide();
      files[".env.example"] = this.rubyEnvExample();
      Object.assign(files, generateUiFiles("rails", manifest));
      return files;
    }

    if (fw === "laravel") {
      files["app/Http/Controllers/StripeController.php"] = this.laravelController(manifest);
      files["routes/stripe.php"] = this.laravelRoutes();
      files["docs/STRIPE-LARAVEL.md"] = this.laravelSetupGuide();
      files[".env.example"] = this.phpEnvExample();
      Object.assign(files, generateUiFiles("laravel", manifest));
      return files;
    }

    files[`${lib}/stripe.ts`] = this.stripeClient();
    files[`${lib}/stripe-config.ts`] = this.stripeConfig(manifest, lib, isNext);
    files[`${lib}/stripe-webhooks.ts`] = this.webhookDispatcher(lib);

    if (isNext && useAppRouter) {
      files["app/api/stripe/webhook/route.ts"] = this.webhookRouteApp();
      files["app/api/stripe/checkout/route.ts"] = this.checkoutApiRoute(manifest);
      files["app/api/stripe/portal/route.ts"] = this.billingPortalRoute();
      files["app/pricing/page.tsx"] = this.pricingPage(manifest);
      files["app/success/page.tsx"] = this.successPage();
      files["app/account/page.tsx"] = this.accountPage();
      files["components/CheckoutButton.tsx"] = this.checkoutButton();
      files["components/ManageSubscriptionButton.tsx"] = this.manageSubscriptionButton();
      files["components/StripeProvider.tsx"] = this.stripeProvider();
    } else if (isNext) {
      files["pages/api/stripe/webhook.ts"] = this.webhookRoutePages();
      files["pages/api/stripe/checkout.ts"] = this.checkoutApiRoutePages(manifest);
      files["pages/api/stripe/portal.ts"] = this.billingPortalRoutePages();
      files["pages/pricing.tsx"] = this.pricingPage(manifest);
      files["pages/success.tsx"] = this.successPage();
      files["pages/account.tsx"] = this.accountPage();
      files["components/CheckoutButton.tsx"] = this.checkoutButton();
      files["components/ManageSubscriptionButton.tsx"] = this.manageSubscriptionButton();
    } else if (this.profile.framework === "express") {
      files["src/routes/stripe.ts"] = this.expressRoutes(manifest);
      Object.assign(files, generateUiFiles("express", manifest));
    } else if (this.profile.framework === "fastify") {
      files["src/plugins/stripe.ts"] = this.fastifyPlugin(manifest);
      Object.assign(files, generateUiFiles("fastify", manifest));
    } else if (this.profile.framework === "remix") {
      files["app/routes/api.stripe.webhook.ts"] = this.remixWebhookRoute();
      files["app/routes/api.stripe.checkout.ts"] = this.remixCheckoutRoute(manifest);
      files["app/routes/api.stripe.portal.ts"] = this.remixPortalRoute();
      Object.assign(files, generateUiFiles("remix", manifest));
    } else if (this.profile.framework === "nuxt") {
      files["server/api/stripe/webhook.post.ts"] = this.nuxtWebhookRoute();
      files["server/api/stripe/checkout.post.ts"] = this.nuxtCheckoutRoute(manifest);
      files["server/api/stripe/portal.post.ts"] = this.nuxtPortalRoute();
      Object.assign(files, generateUiFiles("nuxt", manifest));
    } else if (this.profile.framework === "sveltekit") {
      files["src/routes/api/stripe/webhook/+server.ts"] = this.sveltekitWebhookRoute();
      files["src/routes/api/stripe/checkout/+server.ts"] = this.sveltekitCheckoutRoute(manifest);
      files["src/routes/api/stripe/portal/+server.ts"] = this.sveltekitPortalRoute();
      Object.assign(files, generateUiFiles("sveltekit", manifest));
    } else if (this.profile.framework === "react") {
      Object.assign(files, generateUiFiles("react", manifest));
    } else if (cap.codegen === "minimal") {
      files["docs/STRIPE-WIRING.md"] = this.wiringGuide(manifest);
    }

    files[".env.example"] = this.envExample();
    Object.assign(files, generateSessionInfoRoute(this.profile));
    Object.assign(files, generateAuthIntegration(this.profile));
    return files;
  }

  getPlannedPaths(): string[] {
    return Object.keys(this.generateAll());
  }

  private stripeClient(): string {
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

  private stripeConfig(manifest?: StripeManifest | null, libPath = "lib", isNext = false): string {
    const prices = manifest?.prices ?? [];
    const priceEntries = prices
      .map((p) => {
        const key = `"${tierKey(p.tier)}"`;
        const label = formatAmount(p.amount, p.currency) + (p.interval ? `/${p.interval}` : "");
        const trial = p.trialDays ? `, ${p.trialDays}-day trial` : "";
        return `  ${key}: { id: "${p.id}", label: "${p.tier}", price: "${label}"${trial ? `, trialDays: ${p.trialDays}` : ""} },`;
      })
      .join("\n");

    const featureEntries = prices
      .filter((p) => p.features?.length)
      .map((p) => `  "${tierKey(p.tier)}": ${JSON.stringify(p.features)},`)
      .join("\n");

    return `/**
 * Stripe catalog — auto-generated by stripe-installer.
 * Re-run: stripe-installer automate --provision
 */
export const STRIPE_PRICES = {
${priceEntries || "  // Run stripe-installer automate --provision first"}
} as const;

export type PriceTier = keyof typeof STRIPE_PRICES;

export const TIER_FEATURES: Partial<Record<PriceTier, string[]>> = {
${featureEntries}
};

export const APP_URL = process.env.${isNext ? "NEXT_PUBLIC_APP_URL ?? process.env.APP_URL" : "APP_URL"} ?? "http://localhost:3000";
export const STRIPE_PUBLISHABLE_KEY = process.env.${isNext ? "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? process.env.STRIPE_PUBLISHABLE_KEY" : "STRIPE_PUBLISHABLE_KEY"} ?? "";
`;
  }

  private webhookDispatcher(libPath = "lib"): string {
    const dbModule =
      libPath === "lib" ? "@/lib/stripe-db" : "./stripe-db.js";
    return `import type Stripe from "stripe";

export type WebhookHandler = (event: Stripe.Event) => Promise<void>;

const handlers = new Map<string, WebhookHandler>();

export function onStripeEvent(type: string, handler: WebhookHandler) {
  handlers.set(type, handler);
}

export async function dispatchStripeEvent(event: Stripe.Event): Promise<void> {
  const handler = handlers.get(event.type);
  if (handler) await handler(event);
}

async function withDatabase(
  event: Stripe.Event,
  fn: (db: typeof import("${dbModule}")) => Promise<void>
) {
  if (!process.env.DATABASE_URL) return;
  try {
    const db = await import("${dbModule}");
    await db.recordWebhookEvent(event);
    await fn(db);
  } catch (err) {
    console.error("[stripe] Database sync failed:", err instanceof Error ? err.message : err);
  }
}

// Default handlers — extend with onStripeEvent() in your app
onStripeEvent("checkout.session.completed", async (event) => {
  const session = event.data.object as Stripe.Checkout.Session;
  console.log("[stripe] Checkout completed:", session.id, session.customer);
  await withDatabase(event, async (db) => {
    await db.linkCustomerFromCheckout(session);
  });
});

onStripeEvent("customer.subscription.created", async (event) => {
  const sub = event.data.object as Stripe.Subscription;
  await withDatabase(event, (db) => db.syncSubscriptionFromStripe(sub));
});

onStripeEvent("customer.subscription.updated", async (event) => {
  const sub = event.data.object as Stripe.Subscription;
  await withDatabase(event, (db) => db.syncSubscriptionFromStripe(sub));
});

onStripeEvent("customer.subscription.deleted", async (event) => {
  const sub = event.data.object as Stripe.Subscription;
  await withDatabase(event, (db) => db.syncSubscriptionFromStripe(sub));
});

onStripeEvent("invoice.payment_failed", async (event) => {
  const invoice = event.data.object as Stripe.Invoice;
  console.log("[stripe] Payment failed:", invoice.id, invoice.customer);
});
`;
  }

  private webhookRouteApp(): string {
    return `import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import { dispatchStripeEvent } from "@/lib/stripe-webhooks";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const signature = req.headers.get("stripe-signature");

  if (!signature || !process.env.STRIPE_WEBHOOK_SECRET) {
    return NextResponse.json({ error: "Missing signature or webhook secret" }, { status: 400 });
  }

  try {
    const event = stripe.webhooks.constructEvent(body, signature, process.env.STRIPE_WEBHOOK_SECRET);
    await dispatchStripeEvent(event);
    return NextResponse.json({ received: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Webhook verification failed";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
`;
  }

  private webhookRoutePages(): string {
    return `import type { NextApiRequest, NextApiResponse } from "next";
import { buffer } from "node:stream/consumers";
import { stripe } from "@/lib/stripe";
import { dispatchStripeEvent } from "@/lib/stripe-webhooks";

export const config = { api: { bodyParser: false } };

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).end();

  const rawBody = await buffer(req);
  const signature = req.headers["stripe-signature"] as string;

  try {
    const event = stripe.webhooks.constructEvent(
      rawBody,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
    await dispatchStripeEvent(event);
    res.json({ received: true });
  } catch (err) {
    res.status(400).send(\`Webhook Error: \${(err as Error).message}\`);
  }
}
`;
  }

  private checkoutApiRoute(manifest?: StripeManifest | null): string {
    const hasSubscriptions = manifest?.prices.some((p) => p.interval);
    const hasTrials = manifest?.prices.some((p) => p.trialDays);

    return `import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import { STRIPE_PRICES, APP_URL, type PriceTier } from "@/lib/stripe-config";

export async function POST(req: NextRequest) {
  const { tier, priceId, customerId, customerEmail, mode, userId } = await req.json();

  const tierConfig = tier ? STRIPE_PRICES[tier as PriceTier] : undefined;
  const resolvedPriceId = priceId ?? tierConfig?.id;
  if (!resolvedPriceId) {
    return NextResponse.json({ error: "Invalid tier or priceId" }, { status: 400 });
  }

  const checkoutMode = mode ?? (${hasSubscriptions ? '"subscription"' : '"payment"'});

  const session = await stripe.checkout.sessions.create({
    mode: checkoutMode,
    customer: customerId,
    customer_email: customerId ? undefined : customerEmail,
    line_items: [{ price: resolvedPriceId, quantity: 1 }],
    success_url: \`\${APP_URL}/success?session_id={CHECKOUT_SESSION_ID}\`,
    cancel_url: \`\${APP_URL}/pricing\`,
    allow_promotion_codes: true,
    client_reference_id: userId,
    ${hasSubscriptions ? `subscription_data: {
      metadata: { tier: tier ?? "unknown" },
      ${hasTrials ? "trial_settings: { end_behavior: { missing_payment_method: 'cancel' } }," : ""}
    },` : ""}
    metadata: { tier: tier ?? "unknown" },
  });

  return NextResponse.json({ url: session.url, sessionId: session.id });
}
`;
  }

  private checkoutApiRoutePages(manifest?: StripeManifest | null): string {
    const hasSubscriptions = manifest?.prices.some((p) => p.interval);
    return `import type { NextApiRequest, NextApiResponse } from "next";
import { stripe } from "@/lib/stripe";
import { STRIPE_PRICES, APP_URL, type PriceTier } from "@/lib/stripe-config";

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).end();

  const { tier, priceId, customerId, customerEmail } = req.body;
  const tierConfig = tier ? STRIPE_PRICES[tier as PriceTier] : undefined;
  const resolvedPriceId = priceId ?? tierConfig?.id;

  if (!resolvedPriceId) return res.status(400).json({ error: "Invalid tier or priceId" });

  const session = await stripe.checkout.sessions.create({
    mode: ${hasSubscriptions ? '"subscription"' : '"payment"'},
    customer: customerId,
    customer_email: customerId ? undefined : customerEmail,
    line_items: [{ price: resolvedPriceId, quantity: 1 }],
    success_url: \`\${APP_URL}/success?session_id={CHECKOUT_SESSION_ID}\`,
    cancel_url: \`\${APP_URL}/pricing\`,
    allow_promotion_codes: true,
  });

  res.json({ url: session.url, sessionId: session.id });
}
`;
  }

  private billingPortalRoute(): string {
    return `import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import { APP_URL } from "@/lib/stripe-config";

export async function POST(req: NextRequest) {
  const { customerId } = await req.json();
  if (!customerId) {
    return NextResponse.json({ error: "customerId is required" }, { status: 400 });
  }

  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: \`\${APP_URL}/account\`,
  });

  return NextResponse.json({ url: session.url });
}
`;
  }

  private billingPortalRoutePages(): string {
    return `import type { NextApiRequest, NextApiResponse } from "next";
import { stripe } from "@/lib/stripe";
import { APP_URL } from "@/lib/stripe-config";

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).end();
  const { customerId } = req.body;
  if (!customerId) return res.status(400).json({ error: "customerId is required" });

  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: \`\${APP_URL}/account\`,
  });
  res.json({ url: session.url });
}
`;
  }

  private pricingPage(manifest?: StripeManifest | null): string {
    const tiers = manifest?.prices ?? [];
    const tierCards = tiers
      .map((p) => {
        const key = tierKey(p.tier);
        const label = formatAmount(p.amount, p.currency) + (p.interval ? `/${p.interval}` : "");
        const trial = p.trialDays ? `\n          <p className="text-sm text-green-600">${p.trialDays}-day free trial</p>` : "";
        const features = (p.features ?? [])
          .map((f) => `            <li>${f}</li>`)
          .join("\n");
        const featureList = features
          ? `\n          <ul className="mt-4 space-y-2 text-sm">\n${features}\n          </ul>`
          : "";

        return `        <div className="flex flex-col rounded-xl border p-6 shadow-sm">
          <h2 className="text-xl font-semibold">${p.tier}</h2>
          <p className="mt-2 text-3xl font-bold">${label}</p>${trial}${featureList}
          <CheckoutButton tier="${key}" className="mt-6 rounded-lg bg-black px-4 py-2 text-white disabled:opacity-50" />
        </div>`;
      })
      .join("\n");

    return `"use client";

import { CheckoutButton } from "@/components/CheckoutButton";

export default function PricingPage() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-16">
      <h1 className="text-center text-4xl font-bold">Choose your plan</h1>
      <p className="mt-2 text-center text-gray-600">Simple, transparent pricing</p>
      <div className="mt-12 grid gap-8 md:grid-cols-${Math.min(Math.max(tiers.length, 1), 3)}">
${tierCards || `        <p className="text-center col-span-full">Run stripe-installer automate --provision to create tiers.</p>`}
      </div>
    </main>
  );
}
`;
  }

  private successPage(): string {
    return `"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useEffect } from "react";

export default function SuccessPage() {
  const params = useSearchParams();
  const sessionId = params.get("session_id");

  useEffect(() => {
    if (!sessionId) return;
    fetch("/api/stripe/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.customerId) localStorage.setItem("stripe_customer_id", data.customerId);
      })
      .catch(() => undefined);
  }, [sessionId]);

  return (
    <main className="mx-auto max-w-lg px-4 py-24 text-center">
      <h1 className="text-3xl font-bold text-green-600">Payment successful</h1>
      <p className="mt-4 text-gray-600">Thank you for your purchase.</p>
      {sessionId && <p className="mt-2 text-xs text-gray-400">Session: {sessionId}</p>}
      <Link href="/account" className="mt-8 inline-block rounded-lg bg-black px-6 py-2 text-white">
        Go to account
      </Link>
    </main>
  );
}
`;
  }

  private accountPage(): string {
    return `"use client";

import { ManageSubscriptionButton } from "@/components/ManageSubscriptionButton";

export default function AccountPage() {
  // TODO: Replace with your auth user's Stripe customer ID from database
  const customerId = typeof window !== "undefined"
    ? localStorage.getItem("stripe_customer_id")
    : null;

  return (
    <main className="mx-auto max-w-lg px-4 py-16">
      <h1 className="text-2xl font-bold">Account</h1>
      <p className="mt-2 text-gray-600">Manage your subscription and billing.</p>
      {customerId ? (
        <ManageSubscriptionButton
          customerId={customerId}
          className="mt-6 rounded-lg border px-4 py-2 hover:bg-gray-50"
        />
      ) : (
        <p className="mt-6 text-sm text-gray-500">
          No Stripe customer linked. Complete checkout first.
        </p>
      )}
    </main>
  );
}
`;
  }

  private checkoutButton(): string {
    return `"use client";

import { useState } from "react";
import type { PriceTier } from "@/lib/stripe-config";

interface CheckoutButtonProps {
  tier: PriceTier;
  label?: string;
  className?: string;
}

export function CheckoutButton({ tier, label, className }: CheckoutButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCheckout() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Checkout failed");
      if (data.url) window.location.href = data.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button onClick={handleCheckout} disabled={loading} className={className}>
        {loading ? "Loading..." : (label ?? "Subscribe")}
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
`;
  }

  private manageSubscriptionButton(): string {
    return `"use client";

import { useState } from "react";

interface ManageSubscriptionButtonProps {
  customerId: string;
  label?: string;
  className?: string;
}

export function ManageSubscriptionButton({ customerId, label, className }: ManageSubscriptionButtonProps) {
  const [loading, setLoading] = useState(false);

  async function openPortal() {
    setLoading(true);
    try {
      const res = await fetch("/api/stripe/portal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customerId }),
      });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } finally {
      setLoading(false);
    }
  }

  return (
    <button onClick={openPortal} disabled={loading} className={className}>
      {loading ? "Loading..." : (label ?? "Manage subscription")}
    </button>
  );
}
`;
  }

  private stripeProvider(): string {
    return `"use client";

import { Elements } from "@stripe/react-stripe-js";
import { loadStripe } from "@stripe/stripe-js";
import { STRIPE_PUBLISHABLE_KEY } from "@/lib/stripe-config";

const stripePromise = STRIPE_PUBLISHABLE_KEY ? loadStripe(STRIPE_PUBLISHABLE_KEY) : null;

export function StripeProvider({ children }: { children: React.ReactNode }) {
  if (!stripePromise) return <>{children}</>;
  return <Elements stripe={stripePromise}>{children}</Elements>;
}
`;
  }

  private expressRoutes(manifest?: StripeManifest | null): string {
    const priceComment = manifest?.prices.map((p) => `// ${p.tier}: ${p.id}`).join("\n") ?? "";
    return `import { Router, raw } from "express";
import { stripe } from "../lib/stripe.js";
import { dispatchStripeEvent } from "../lib/stripe-webhooks.js";

const router = Router();

${priceComment}

// IMPORTANT: mount this router BEFORE app.use(express.json()) or use raw() as below
router.post("/webhook", raw({ type: "application/json" }), async (req, res) => {
  const signature = req.headers["stripe-signature"] as string;
  try {
    const event = stripe.webhooks.constructEvent(req.body, signature, process.env.STRIPE_WEBHOOK_SECRET!);
    await dispatchStripeEvent(event);
    res.json({ received: true });
  } catch (err) {
    res.status(400).send(\`Webhook Error: \${(err as Error).message}\`);
  }
});

router.post("/checkout", async (req, res) => {
  const { priceId, customerEmail } = req.body;
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer_email: customerEmail,
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: \`\${process.env.APP_URL}/success.html\`,
    cancel_url: \`\${process.env.APP_URL}/pricing.html\`,
  });
  res.json({ url: session.url });
});

router.post("/portal", async (req, res) => {
  const { customerId } = req.body;
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: \`\${process.env.APP_URL}/account.html\`,
  });
  res.json({ url: session.url });
});

router.post("/session", async (req, res) => {
  const { sessionId } = req.body;
  if (!sessionId) return res.status(400).json({ error: "sessionId required" });
  try {
    const session = await stripe.checkout.sessions.retrieve(sessionId);
    const customerId = typeof session.customer === "string" ? session.customer : session.customer?.id ?? null;
    res.json({
      customerId,
      email: session.customer_email ?? session.customer_details?.email ?? null,
      status: session.status,
    });
  } catch (err) {
    res.status(400).json({ error: err instanceof Error ? err.message : "Invalid session" });
  }
});

export default router;
`;
  }

  private fastifyPlugin(manifest?: StripeManifest | null): string {
    const priceComment = manifest?.prices.map((p) => `// ${p.tier}: ${p.id}`).join("\n") ?? "";
    return `import type { FastifyPluginAsync } from "fastify";
import { stripe } from "../lib/stripe.js";
import { dispatchStripeEvent } from "../lib/stripe-webhooks.js";

${priceComment}

const stripePlugin: FastifyPluginAsync = async (app) => {
  app.post("/stripe/webhook", {
    config: { rawBody: true },
  }, async (req, reply) => {
    const signature = req.headers["stripe-signature"] as string;
    const rawBody = (req as { rawBody?: Buffer }).rawBody ?? req.body;
    try {
      const event = stripe.webhooks.constructEvent(
        rawBody as Buffer,
        signature,
        process.env.STRIPE_WEBHOOK_SECRET!
      );
      await dispatchStripeEvent(event);
      return reply.send({ received: true });
    } catch (err) {
      return reply.status(400).send(\`Webhook Error: \${(err as Error).message}\`);
    }
  });

  app.post("/stripe/checkout", async (req, reply) => {
    const { priceId, customerEmail } = req.body as { priceId: string; customerEmail?: string };
    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer_email: customerEmail,
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: \`\${process.env.APP_URL}/success.html\`,
      cancel_url: \`\${process.env.APP_URL}/pricing.html\`,
    });
    return reply.send({ url: session.url });
  });

  app.post("/stripe/portal", async (req, reply) => {
    const { customerId } = req.body as { customerId: string };
    const session = await stripe.billingPortal.sessions.create({
      customer: customerId,
      return_url: \`\${process.env.APP_URL}/account.html\`,
    });
    return reply.send({ url: session.url });
  });
};

export default stripePlugin;
// Register: await app.register(stripePlugin) — enable rawBody in server config for webhooks
`;
  }

  private remixWebhookRoute(): string {
    return `import type { ActionFunctionArgs } from "@remix-run/node";
import { stripe } from "~/lib/stripe";
import { dispatchStripeEvent } from "~/lib/stripe-webhooks";

export async function action({ request }: ActionFunctionArgs) {
  const body = await request.text();
  const signature = request.headers.get("stripe-signature");
  if (!signature || !process.env.STRIPE_WEBHOOK_SECRET) {
    return new Response("Missing signature", { status: 400 });
  }
  try {
    const event = stripe.webhooks.constructEvent(body, signature, process.env.STRIPE_WEBHOOK_SECRET);
    await dispatchStripeEvent(event);
    return new Response(JSON.stringify({ received: true }), { status: 200 });
  } catch (err) {
    return new Response(\`Webhook Error: \${(err as Error).message}\`, { status: 400 });
  }
}
`;
  }

  private remixCheckoutRoute(manifest?: StripeManifest | null): string {
    void manifest;
    return `import type { ActionFunctionArgs } from "@remix-run/node";
import { stripe } from "~/lib/stripe";

export async function action({ request }: ActionFunctionArgs) {
  const { priceId, customerEmail } = await request.json();
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer_email: customerEmail,
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: \`\${process.env.APP_URL}/success?session_id={CHECKOUT_SESSION_ID}\`,
    cancel_url: \`\${process.env.APP_URL}/pricing\`,
  });
  return Response.json({ url: session.url });
}
`;
  }

  private remixPortalRoute(): string {
    return `import type { ActionFunctionArgs } from "@remix-run/node";
import { stripe } from "~/lib/stripe";

export async function action({ request }: ActionFunctionArgs) {
  const { customerId } = await request.json();
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: \`\${process.env.APP_URL}/account\`,
  });
  return Response.json({ url: session.url });
}
`;
  }

  private nuxtWebhookRoute(): string {
    return `import { readRawBody, getHeader, createError } from "h3";
import { stripe } from "../../utils/stripe";
import { dispatchStripeEvent } from "../../utils/stripe-webhooks";

export default defineEventHandler(async (event) => {
  const body = await readRawBody(event);
  const signature = getHeader(event, "stripe-signature");
  if (!signature || !process.env.STRIPE_WEBHOOK_SECRET) {
    throw createError({ statusCode: 400, statusMessage: "Missing signature or webhook secret" });
  }
  try {
    const payload = body instanceof Buffer ? body : Buffer.from(body ?? "");
    const stripeEvent = stripe.webhooks.constructEvent(
      payload,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET
    );
    await dispatchStripeEvent(stripeEvent);
    return { received: true };
  } catch (err) {
    throw createError({
      statusCode: 400,
      statusMessage: \`Webhook Error: \${(err as Error).message}\`,
    });
  }
});
`;
  }

  private nuxtCheckoutRoute(manifest?: StripeManifest | null): string {
    void manifest;
    return `import { readBody, createError } from "h3";
import { stripe } from "../../utils/stripe";

export default defineEventHandler(async (event) => {
  const { priceId, customerEmail } = await readBody<{ priceId: string; customerEmail?: string }>(event);
  if (!priceId) throw createError({ statusCode: 400, statusMessage: "priceId required" });
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer_email: customerEmail,
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: \`\${process.env.APP_URL}/success?session_id={CHECKOUT_SESSION_ID}\`,
    cancel_url: \`\${process.env.APP_URL}/pricing\`,
  });
  return { url: session.url };
});
`;
  }

  private nuxtPortalRoute(): string {
    return `import { readBody, createError } from "h3";
import { stripe } from "../../utils/stripe";

export default defineEventHandler(async (event) => {
  const { customerId } = await readBody<{ customerId: string }>(event);
  if (!customerId) throw createError({ statusCode: 400, statusMessage: "customerId required" });
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: \`\${process.env.APP_URL}/account\`,
  });
  return { url: session.url };
});
`;
  }

  private sveltekitWebhookRoute(): string {
    return `import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { stripe } from "$lib/stripe";
import { dispatchStripeEvent } from "$lib/stripe-webhooks";

export const POST: RequestHandler = async ({ request }) => {
  const body = await request.text();
  const signature = request.headers.get("stripe-signature");
  if (!signature || !process.env.STRIPE_WEBHOOK_SECRET) {
    throw error(400, "Missing signature or webhook secret");
  }
  try {
    const event = stripe.webhooks.constructEvent(body, signature, process.env.STRIPE_WEBHOOK_SECRET);
    await dispatchStripeEvent(event);
    return json({ received: true });
  } catch (err) {
    throw error(400, \`Webhook Error: \${(err as Error).message}\`);
  }
};
`;
  }

  private sveltekitCheckoutRoute(manifest?: StripeManifest | null): string {
    void manifest;
    return `import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { stripe } from "$lib/stripe";

export const POST: RequestHandler = async ({ request }) => {
  const { priceId, customerEmail } = await request.json();
  if (!priceId) throw error(400, "priceId required");
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer_email: customerEmail,
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: \`\${process.env.APP_URL}/success?session_id={CHECKOUT_SESSION_ID}\`,
    cancel_url: \`\${process.env.APP_URL}/pricing\`,
  });
  return json({ url: session.url });
};
`;
  }

  private sveltekitPortalRoute(): string {
    return `import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
import { stripe } from "$lib/stripe";

export const POST: RequestHandler = async ({ request }) => {
  const { customerId } = await request.json();
  if (!customerId) throw error(400, "customerId required");
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: \`\${process.env.APP_URL}/account\`,
  });
  return json({ url: session.url });
};
`;
  }

  private djangoStripeClient(): string {
    return `import os
import stripe

if not os.environ.get("STRIPE_SECRET_KEY"):
    raise RuntimeError("STRIPE_SECRET_KEY is not set")

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
`;
  }

  private djangoViews(manifest?: StripeManifest | null): string {
    const priceComment =
      manifest?.prices.map((p) => `# ${p.tier}: ${p.id}`).join("\n") ?? "# Run stripe-installer run --provision first";
    return `import json
import os

import stripe
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import client  # noqa: F401 — configures stripe.api_key

${priceComment}


@csrf_exempt
@require_POST
def webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not sig_header or not secret:
        return HttpResponse("Missing signature or webhook secret", status=400)
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError:
        return HttpResponse("Invalid payload", status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse("Invalid signature", status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print(f"[stripe] Checkout completed: {session.get('id')}")
    elif event["type"] in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        sub = event["data"]["object"]
        print(f"[stripe] Subscription {event['type']}: {sub.get('id')}")
    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        print(f"[stripe] Payment failed: {invoice.get('id')}")

    return JsonResponse({"received": True})


@csrf_exempt
@require_POST
def checkout(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    price_id = data.get("priceId")
    if not price_id:
        return JsonResponse({"error": "priceId required"}, status=400)
    app_url = os.environ.get("APP_URL", "http://localhost:8000")
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=data.get("customerEmail"),
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{app_url}/stripe/success/",
        cancel_url=f"{app_url}/stripe/pricing/",
    )
    return JsonResponse({"url": session.url})


@csrf_exempt
@require_POST
def portal(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    customer_id = data.get("customerId")
    if not customer_id:
        return JsonResponse({"error": "customerId required"}, status=400)
    app_url = os.environ.get("APP_URL", "http://localhost:8000")
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{app_url}/stripe/account/",
    )
    return JsonResponse({"url": session.url})
`;
  }

  private djangoSetupGuide(): string {
    return `# Stripe — Django setup

## 1. Install dependency
\`\`\`bash
pip install stripe
\`\`\`

## 2. Wire URLs
In your project \`urls.py\`:
\`\`\`python
from django.urls import include, path

urlpatterns = [
    # ...
    path("stripe/", include("stripe.urls")),
]
\`\`\`

Webhook URL for Stripe Dashboard: \`\${APP_URL}/stripe/webhook\`

## 3. Environment
Copy \`.env.example\` keys into your environment or \`.env\` (never commit secrets).

## 4. CSRF
Webhook/checkout/portal views use \`@csrf_exempt\` — restrict to POST-only in production as needed.
`;
  }

  private flaskBlueprint(manifest?: StripeManifest | null): string {
    const priceComment =
      manifest?.prices.map((p) => `# ${p.tier}: ${p.id}`).join("\n") ?? "# Run stripe-installer run --provision first";
    return `import json
import os

import stripe
from flask import Blueprint, jsonify, render_template, request

stripe_bp = Blueprint("stripe", __name__, url_prefix="/stripe")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

${priceComment}


@stripe_bp.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not sig_header or not secret:
        return "Missing signature or webhook secret", 400
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        print(f"[stripe] Checkout completed: {session.get('id')}")
    elif event["type"] in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        sub = event["data"]["object"]
        print(f"[stripe] Subscription {event['type']}: {sub.get('id')}")

    return jsonify({"received": True})


@stripe_bp.route("/checkout", methods=["POST"])
def checkout():
    data = request.get_json(silent=True) or {}
    price_id = data.get("priceId")
    if not price_id:
        return jsonify({"error": "priceId required"}), 400
    app_url = os.environ.get("APP_URL", "http://localhost:5000")
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=data.get("customerEmail"),
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{app_url}/stripe/success",
        cancel_url=f"{app_url}/stripe/pricing",
    )
    return jsonify({"url": session.url})


@stripe_bp.route("/portal", methods=["POST"])
def portal():
    data = request.get_json(silent=True) or {}
    customer_id = data.get("customerId")
    if not customer_id:
        return jsonify({"error": "customerId required"}), 400
    app_url = os.environ.get("APP_URL", "http://localhost:5000")
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{app_url}/stripe/account",
    )
    return jsonify({"url": session.url})
${flaskPageRoutes()}
`;
  }

  private flaskSetupGuide(): string {
    return `# Stripe — Flask setup

## 1. Install dependency
\`\`\`bash
pip install stripe flask
\`\`\`

## 2. Register blueprint
\`\`\`python
from stripe_routes import stripe_bp

app.register_blueprint(stripe_bp)
\`\`\`

Webhook URL for Stripe Dashboard: \`\${APP_URL}/stripe/webhook\`

## 3. Environment
Mount webhook **before** any middleware that parses JSON bodies globally if you add custom parsers.
`;
  }

  private pythonEnvExample(): string {
    return `# Stripe — copy to .env (never commit real keys)
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
APP_URL=http://localhost:8000
`;
  }

  private rubyEnvExample(): string {
    return `# Stripe — copy to .env (never commit real keys)
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
APP_URL=http://localhost:3000
`;
  }

  private phpEnvExample(): string {
    return `# Stripe — copy to .env (never commit real keys)
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
APP_URL=http://localhost:8000
`;
  }

  private railsController(manifest?: StripeManifest | null): string {
    const priceComment =
      manifest?.prices.map((p) => `# ${p.tier}: ${p.id}`).join("\n") ?? "# Run stripe-installer run --provision first";
    return `# frozen_string_literal: true

require "stripe"
require "json"

Stripe.api_key = ENV.fetch("STRIPE_SECRET_KEY")

${priceComment}

class StripeController < ApplicationController
  skip_before_action :verify_authenticity_token, only: %i[webhook checkout portal session_info]

  def webhook
    payload = request.body.read
    sig_header = request.env["HTTP_STRIPE_SIGNATURE"]
    secret = ENV["STRIPE_WEBHOOK_SECRET"]
    return head :bad_request if sig_header.blank? || secret.blank?

    event = Stripe::Webhook.construct_event(payload, sig_header, secret)
    Rails.logger.info "[stripe] \#{event.type}"
    render json: { received: true }
  rescue JSON::ParserError, Stripe::SignatureVerificationError
    head :bad_request
  end

  def checkout
    data = JSON.parse(request.body.read)
    price_id = data["priceId"]
    return render json: { error: "priceId required" }, status: :bad_request if price_id.blank?

    app_url = ENV.fetch("APP_URL", "http://localhost:3000")
    session = Stripe::Checkout::Session.create(
      mode: "subscription",
      customer_email: data["customerEmail"],
      line_items: [{ price: price_id, quantity: 1 }],
      success_url: "\#{app_url}/stripe/success?session_id={CHECKOUT_SESSION_ID}",
      cancel_url: "\#{app_url}/stripe/pricing"
    )
    render json: { url: session.url }
  end

  def portal
    data = JSON.parse(request.body.read)
    customer_id = data["customerId"]
    return render json: { error: "customerId required" }, status: :bad_request if customer_id.blank?

    app_url = ENV.fetch("APP_URL", "http://localhost:3000")
    session = Stripe::BillingPortal::Session.create(
      customer: customer_id,
      return_url: "\#{app_url}/stripe/account"
    )
    render json: { url: session.url }
  end

  def pricing
    render :pricing
  end

  def success
    render :success
  end

  def account
    render :account
  end

  def session_info
    data = JSON.parse(request.body.read)
    session_id = data["sessionId"]
    return render json: { error: "sessionId required" }, status: :bad_request if session_id.blank?

    session = Stripe::Checkout::Session.retrieve(session_id)
    customer_id = session.customer.is_a?(String) ? session.customer : session.customer&.id
    render json: { customerId: customer_id, email: session.customer_email, status: session.status }
  rescue Stripe::StripeError => e
    render json: { error: e.message }, status: :bad_request
  end
end
`;
  }

  private railsSetupGuide(): string {
    return `# Stripe — Rails setup

## 1. Gemfile
\`\`\`ruby
gem "stripe"
\`\`\`

## 2. Routes (config/routes.rb)
\`\`\`ruby
scope :stripe do
  post "webhook", to: "stripe#webhook"
  post "checkout", to: "stripe#checkout"
  post "portal", to: "stripe#portal"
  post "session", to: "stripe#session_info"
  get "pricing", to: "stripe#pricing"
  get "success", to: "stripe#success"
  get "account", to: "stripe#account"
end
\`\`\`

Webhook URL: \`\${APP_URL}/stripe/webhook\`
`;
  }

  private laravelController(manifest?: StripeManifest | null): string {
    const priceComment =
      manifest?.prices.map((p) => `// ${p.tier}: ${p.id}`).join("\n") ?? "// Run stripe-installer run --provision first";
    return `<?php

namespace App\\Http\\Controllers;

use Illuminate\\Http\\Request;
use Stripe\\Stripe;
use Stripe\\Webhook;
use Stripe\\Checkout\\Session as CheckoutSession;
use Stripe\\BillingPortal\\Session as PortalSession;

${priceComment}

class StripeController extends Controller
{
    public function __construct()
    {
        Stripe::setApiKey(env('STRIPE_SECRET_KEY'));
    }

    public function webhook(Request $request)
    {
        $payload = $request->getContent();
        $sig = $request->header('Stripe-Signature');
        $secret = env('STRIPE_WEBHOOK_SECRET');
        if (!$sig || !$secret) {
            return response('Missing signature', 400);
        }
        try {
            $event = Webhook::constructEvent($payload, $sig, $secret);
        } catch (\\Exception $e) {
            return response('Invalid signature', 400);
        }
        \\Log::info('[stripe] ' . $event->type);
        return response()->json(['received' => true]);
    }

    public function checkout(Request $request)
    {
        $priceId = $request->input('priceId');
        if (!$priceId) {
            return response()->json(['error' => 'priceId required'], 400);
        }
        $appUrl = env('APP_URL', 'http://localhost:8000');
        $session = CheckoutSession::create([
            'mode' => 'subscription',
            'customer_email' => $request->input('customerEmail'),
            'line_items' => [['price' => $priceId, 'quantity' => 1]],
            'success_url' => $appUrl . '/stripe/success?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url' => $appUrl . '/stripe/pricing',
        ]);
        return response()->json(['url' => $session->url]);
    }

    public function portal(Request $request)
    {
        $customerId = $request->input('customerId');
        if (!$customerId) {
            return response()->json(['error' => 'customerId required'], 400);
        }
        $appUrl = env('APP_URL', 'http://localhost:8000');
        $session = PortalSession::create([
            'customer' => $customerId,
            'return_url' => $appUrl . '/stripe/account',
        ]);
        return response()->json(['url' => $session->url]);
    }

    public function pricing()
    {
        return view('stripe.pricing');
    }

    public function success()
    {
        return view('stripe.success');
    }

    public function account()
    {
        return view('stripe.account');
    }

    public function sessionInfo(Request $request)
    {
        $sessionId = $request->input('sessionId');
        if (!$sessionId) {
            return response()->json(['error' => 'sessionId required'], 400);
        }
        try {
            $session = CheckoutSession::retrieve($sessionId);
        } catch (\Exception $e) {
            return response()->json(['error' => $e->getMessage()], 400);
        }
        $customerId = is_string($session->customer) ? $session->customer : ($session->customer->id ?? null);
        return response()->json([
            'customerId' => $customerId,
            'email' => $session->customer_email,
            'status' => $session->status,
        ]);
    }
}
`;
  }

  private laravelRoutes(): string {
    return `<?php

use App\\Http\\Controllers\\StripeController;
use Illuminate\\Support\\Facades\\Route;

Route::prefix('stripe')->group(function () {
    Route::post('/webhook', [StripeController::class, 'webhook']);
    Route::post('/checkout', [StripeController::class, 'checkout']);
    Route::post('/portal', [StripeController::class, 'portal']);
    Route::post('/session', [StripeController::class, 'sessionInfo']);
    Route::get('/pricing', [StripeController::class, 'pricing']);
    Route::get('/success', [StripeController::class, 'success']);
    Route::get('/account', [StripeController::class, 'account']);
});
`;
  }

  private laravelSetupGuide(): string {
    return `# Stripe — Laravel setup

## 1. Install
\`\`\`bash
composer require stripe/stripe-php
\`\`\`

## 2. Load routes
In \`bootstrap/app.php\` or \`RouteServiceProvider\`, require \`routes/stripe.php\`.

Webhook URL: \`\${APP_URL}/stripe/webhook\`
`;
  }

  private manualSetupGuide(): string {
    const cap = getFrameworkCapabilities(this.profile.framework);
    return `# Stripe Setup — ${cap.displayName}

${cap.summary}

## Steps
1. Store keys in vault: \`stripe-installer vault set STRIPE_SECRET_KEY\`
2. Provision catalog: \`stripe-installer run --provision\`
3. Implement webhook endpoint at \`${cap.webhookPath}\` with signature verification
4. Use the official Stripe SDK for ${this.profile.language}

See https://docs.stripe.com for ${cap.displayName}-specific guides.
`;
  }

  private wiringGuide(manifest?: StripeManifest | null): string {
    const cap = getFrameworkCapabilities(this.profile.framework);
    const prices = manifest?.prices.map((p) => `- ${p.tier}: \`${p.id}\``).join("\n") ?? "- Run provision first";
    return `# Stripe Wiring — ${cap.displayName}

Generated shared client libraries in \`${libDir(this.profile)}/\`.

## Webhook URL
Register in Stripe Dashboard: \`\${APP_URL}${cap.webhookPath}\`

## Price IDs
${prices}

## ${cap.displayName} notes
${cap.summary}

### React (SPA / Vite)
- Call your backend to create Checkout sessions — never use secret key in browser
- Add a small Express/Fastify server or serverless function for /webhook
`;
  }

  private envExample(): string {
    const isNext = this.profile.framework === "nextjs";
    const pubKey = isNext
      ? "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY="
      : "STRIPE_PUBLISHABLE_KEY=";
    const appUrl = isNext ? "NEXT_PUBLIC_APP_URL=http://localhost:3000" : "APP_URL=http://localhost:3000";
    return `# Stripe — copy to .env.local (never commit real keys)
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
${pubKey}
STRIPE_WEBHOOK_SECRET=
${appUrl}
`;
  }
}
