import { writeFile, readFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import type Stripe from "stripe";
import type {
  PricingTier,
  StripeAutomationConfig,
  StripeAutomationResult,
  StripeManifest,
} from "../types.js";
import { SecretVault } from "../security/vault.js";
import { getStripeClient, verifyApiKeys } from "./stripe-client.js";
import { formatAmount } from "./tier-format.js";
import { emitEvent, type PipelineEventHandler } from "./pipeline-events.js";

const INSTALLER_TAG = "stripe-installer";

const DEFAULT_WEBHOOK_EVENTS = [
  "checkout.session.completed",
  "customer.subscription.created",
  "customer.subscription.updated",
  "customer.subscription.deleted",
  "invoice.paid",
  "invoice.payment_failed",
  "customer.created",
  "account.updated",
  "transfer.created",
  "transfer.updated",
  "transfer.reversed",
] as const;

const MANIFEST_DIR = ".stripe-installer";
const MANIFEST_FILE = "stripe-manifest.json";

export class StripeApiAutomation {
  constructor(
    private readonly projectRoot: string,
    private readonly vault: SecretVault
  ) {}

  async run(
    config: StripeAutomationConfig,
    hooks?: { onEvent?: PipelineEventHandler }
  ): Promise<StripeAutomationResult> {
    const onEvent = hooks?.onEvent;
    const verified = await verifyApiKeys(this.vault);
    if (!verified.secretKey.valid) {
      throw new Error(`API key verification failed: ${verified.secretKey.message}`);
    }

    const stripe = await getStripeClient(this.vault);
    const existingManifest = await this.loadManifest();
    const reuse = config.provision?.reuseExisting !== false;
    const warnings: string[] = [];

    const result: StripeAutomationResult = {
      verified,
      products: [],
      prices: [],
      warnings,
    };

    if (config.tiers && config.tiers.length > 0) {
      emitEvent(onEvent, {
        step: "provision.products",
        status: "running",
        message: "Provisioning Stripe products…",
      });
      const catalog = await this.createSubscriptionCatalog(
        stripe,
        config.tiers,
        existingManifest,
        reuse,
        onEvent
      );
      result.products = catalog.products;
      result.prices = catalog.prices;
      emitEvent(onEvent, {
        step: "provision.products",
        status: "ok",
        message: "Products provisioned",
      });
    } else if (config.productName) {
      const product = await this.findOrCreateProduct(stripe, config.productName, config.productDescription, reuse);
      result.products.push({ id: product.id, name: product.name, reused: product.reused });

      if (config.oneTimeAmount) {
        const price = await this.findOrCreatePrice(stripe, {
          productId: product.id,
          amount: config.oneTimeAmount,
          currency: config.currency ?? "usd",
          tierName: "one-time",
        }, reuse);
        result.prices.push({
          id: price.id,
          tier: "one-time",
          amount: config.oneTimeAmount,
          currency: config.currency ?? "usd",
          reused: price.reused,
        });
      }
    }

    if (config.billingPortalReturnUrl && config.provision?.createPortal !== false) {
      const portal = await this.configureBillingPortal(stripe, config.billingPortalReturnUrl, existingManifest, reuse);
      result.billingPortalConfig = { id: portal.id, reused: portal.reused };
    }

    if (config.webhookUrl && config.provision?.createWebhook !== false) {
      emitEvent(onEvent, {
        step: "provision.webhook",
        status: "running",
        message: "Registering webhooks…",
      });
      const webhook = await this.registerWebhook(
        stripe,
        config.webhookUrl,
        config.webhookEvents ?? [...DEFAULT_WEBHOOK_EVENTS]
      );
      result.webhookEndpoint = {
        id: webhook.id,
        url: webhook.url,
        reused: webhook.reused,
      };
      emitEvent(onEvent, {
        step: "provision.webhook",
        status: "ok",
        message: `Webhook registered: ${webhook.url}`,
      });

      if (webhook.secret) {
        await this.vault.set("STRIPE_WEBHOOK_SECRET", webhook.secret);
        result.webhookSecretStored = true;
      } else if (webhook.reused) {
        warnings.push(
          "Webhook endpoint already exists — secret not returned by Stripe. " +
            "Use existing whsec_ from Dashboard or run: stripe listen --print-secret"
        );
      }
    }

    const publishableKey = await this.vault.get("STRIPE_PUBLISHABLE_KEY");
    if (publishableKey) {
      await this.vault.set("NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY", publishableKey);
    }

    const now = new Date().toISOString();
    await this.saveManifest({
      createdAt: existingManifest?.createdAt ?? now,
      updatedAt: now,
      accountId: verified.accountId,
      products: result.products.map(({ id, name }) => ({ id, name })),
      prices: result.prices.map((p) => ({
        id: p.id,
        tier: p.tier,
        amount: p.amount,
        currency: p.currency,
        interval: p.interval,
        trialDays: p.trialDays,
        features: config.tiers?.find((t) => t.name === p.tier)?.features,
      })),
      webhookEndpoint: result.webhookEndpoint,
      billingPortalConfig: result.billingPortalConfig,
      appUrl: config.appUrl,
    });

    return result;
  }

  private async findOrCreateProduct(
    stripe: Stripe,
    name: string,
    description: string | undefined,
    reuse: boolean
  ): Promise<{ id: string; name: string; reused: boolean }> {
    if (reuse) {
      const existing = await this.findProductByName(stripe, name);
      if (existing) return { id: existing.id, name: existing.name, reused: true };
    }

    const product = await stripe.products.create({
      name,
      description,
      metadata: { created_by: INSTALLER_TAG, tier: name },
    });
    return { id: product.id, name: product.name, reused: false };
  }

  private async findProductByName(stripe: Stripe, name: string): Promise<Stripe.Product | null> {
    const products = await stripe.products.list({ limit: 100, active: true });
    return (
      products.data.find(
        (p) => p.name === name && p.metadata?.created_by === INSTALLER_TAG
      ) ?? null
    );
  }

  async createPrice(
    stripe: Stripe,
    opts: {
      productId: string;
      amount: number;
      currency: string;
      interval?: "month" | "year";
      tierName?: string;
      trialDays?: number;
    }
  ): Promise<Stripe.Price> {
    const params: Stripe.PriceCreateParams = {
      product: opts.productId,
      unit_amount: opts.amount,
      currency: opts.currency,
      metadata: { created_by: INSTALLER_TAG, tier: opts.tierName ?? "default" },
    };

    if (opts.interval) {
      params.recurring = { interval: opts.interval };
      if (opts.trialDays && opts.trialDays > 0) {
        params.recurring.trial_period_days = opts.trialDays;
      }
    }

    return stripe.prices.create(params);
  }

  private async findOrCreatePrice(
    stripe: Stripe,
    opts: {
      productId: string;
      amount: number;
      currency: string;
      interval?: "month" | "year";
      tierName?: string;
      trialDays?: number;
    },
    reuse: boolean
  ): Promise<{ id: string; reused: boolean }> {
    if (reuse) {
      const prices = await stripe.prices.list({ product: opts.productId, active: true, limit: 100 });
      const match = prices.data.find(
        (p) =>
          p.unit_amount === opts.amount &&
          p.currency === opts.currency &&
          p.metadata?.created_by === INSTALLER_TAG &&
          p.metadata?.tier === (opts.tierName ?? "default") &&
          (opts.interval
            ? p.recurring?.interval === opts.interval
            : !p.recurring)
      );
      if (match) return { id: match.id, reused: true };
    }

    const price = await this.createPrice(stripe, opts);
    return { id: price.id, reused: false };
  }

  async createSubscriptionCatalog(
    stripe: Stripe,
    tiers: PricingTier[],
    manifest: StripeManifest | null,
    reuse: boolean,
    onEvent?: PipelineEventHandler
  ): Promise<{
    products: StripeAutomationResult["products"];
    prices: StripeAutomationResult["prices"];
  }> {
    const products: StripeAutomationResult["products"] = [];
    const prices: StripeAutomationResult["prices"] = [];

    for (const tier of tiers) {
      const manifestProduct = manifest?.products.find((p) => p.name === tier.name);
      let productId: string;
      let productReused = false;

      if (reuse && manifestProduct) {
        productId = manifestProduct.id;
        productReused = true;
      } else {
        const product = await this.findOrCreateProduct(stripe, tier.name, tier.description, reuse);
        productId = product.id;
        productReused = product.reused;
      }

      products.push({ id: productId, name: tier.name, reused: productReused });

      const manifestPrice = manifest?.prices.find(
        (p) => p.tier === tier.name && p.amount === tier.amount && p.interval === tier.interval
      );

      let priceId: string;
      let priceReused = false;

      if (reuse && manifestPrice) {
        priceId = manifestPrice.id;
        priceReused = true;
      } else {
        const price = await this.findOrCreatePrice(
          stripe,
          {
            productId,
            amount: tier.amount,
            currency: tier.currency,
            interval: tier.interval,
            tierName: tier.name,
            trialDays: tier.trialDays,
          },
          reuse
        );
        priceId = price.id;
        priceReused = price.reused;
      }

      prices.push({
        id: priceId,
        tier: tier.name,
        amount: tier.amount,
        currency: tier.currency,
        interval: tier.interval,
        trialDays: tier.trialDays,
        reused: priceReused,
      });

      if (!priceReused) {
        const label = formatAmount(tier.amount, tier.currency);
        const interval = tier.interval ? `/${tier.interval}` : "";
        emitEvent(onEvent, {
          step: "provision.price",
          status: "detail",
          message: `Created: ${tier.name} (${label}${interval})`,
          detail: true,
        });
      }
    }

    return { products, prices };
  }

  async configureBillingPortal(
    stripe: Stripe,
    returnUrl: string,
    manifest: StripeManifest | null,
    reuse: boolean
  ): Promise<{ id: string; reused: boolean }> {
    if (reuse && manifest?.billingPortalConfig?.id) {
      try {
        const existing = await stripe.billingPortal.configurations.retrieve(
          manifest.billingPortalConfig.id
        );
        if (existing.active) {
          return { id: existing.id, reused: true };
        }
      } catch {
        // create new if stale
      }
    }

    const prices = await stripe.prices.list({ active: true, limit: 50, type: "recurring" });
    const installerPrices = prices.data.filter((p) => p.metadata?.created_by === INSTALLER_TAG);
    const priceIds = (installerPrices.length > 0 ? installerPrices : prices.data)
      .map((p) => p.id)
      .slice(0, 10);

    const portal = await stripe.billingPortal.configurations.create({
      business_profile: { headline: "Manage your subscription" },
      features: {
        customer_update: { enabled: true, allowed_updates: ["email", "address", "name"] },
        invoice_history: { enabled: true },
        payment_method_update: { enabled: true },
        subscription_cancel: { enabled: true, mode: "at_period_end" },
        subscription_update:
          priceIds.length > 0
            ? {
                enabled: true,
                default_allowed_updates: ["price", "promotion_code"],
                products: await this.buildPortalProducts(stripe, priceIds),
              }
            : { enabled: false },
      },
      default_return_url: returnUrl,
      metadata: { created_by: INSTALLER_TAG },
    });

    return { id: portal.id, reused: false };
  }

  private async buildPortalProducts(
    stripe: Stripe,
    priceIds: string[]
  ): Promise<Stripe.BillingPortal.ConfigurationCreateParams.Features.SubscriptionUpdate.Product[]> {
    const productMap = new Map<string, string[]>();

    for (const priceId of priceIds) {
      const price = await stripe.prices.retrieve(priceId);
      const productId = typeof price.product === "string" ? price.product : price.product.id;
      const existing = productMap.get(productId) ?? [];
      existing.push(priceId);
      productMap.set(productId, existing);
    }

    return [...productMap.entries()].map(([product, prices]) => ({ product, prices }));
  }

  async registerWebhook(
    stripe: Stripe,
    url: string,
    events: string[]
  ): Promise<Stripe.WebhookEndpoint & { secret?: string; reused: boolean }> {
    const existing = await stripe.webhookEndpoints.list({ limit: 100 });
    const match = existing.data.find((e) => e.url === url);

    if (match) {
      await stripe.webhookEndpoints.update(match.id, {
        enabled_events: events as Stripe.WebhookEndpointUpdateParams.EnabledEvent[],
        disabled: false,
      });
      return { ...match, reused: true };
    }

    const endpoint = await stripe.webhookEndpoints.create({
      url,
      enabled_events: events as Stripe.WebhookEndpointCreateParams.EnabledEvent[],
      metadata: { created_by: INSTALLER_TAG },
    });
    return { ...endpoint, reused: false };
  }

  async loadManifest(): Promise<StripeManifest | null> {
    try {
      const raw = await readFile(join(this.projectRoot, MANIFEST_DIR, MANIFEST_FILE), "utf8");
      const manifest = JSON.parse(raw) as StripeManifest;
      if (!manifest.updatedAt) manifest.updatedAt = manifest.createdAt;
      return manifest;
    } catch {
      return null;
    }
  }

  async saveManifest(manifest: StripeManifest): Promise<void> {
    const dir = join(this.projectRoot, MANIFEST_DIR);
    await mkdir(dir, { recursive: true });
    await writeFile(join(dir, MANIFEST_FILE), JSON.stringify(manifest, null, 2), "utf8");
  }
}
