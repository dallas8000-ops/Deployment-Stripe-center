import { z } from "zod";
import type { ProjectProfile, StripeAutomationConfig } from "../types.js";
import { resolveWebhookPath } from "./framework-profiles.js";

const pricingTierSchema = z.object({
  name: z.string().min(1),
  description: z.string().optional(),
  amount: z.number().int().positive(),
  currency: z.string().length(3).default("usd"),
  interval: z.enum(["month", "year"]).optional(),
  trialDays: z.number().int().nonnegative().optional(),
  features: z.array(z.string()).optional(),
});

export const stripeConfigSchema = z.object({
  appUrl: z.string().url().optional(),
  webhookUrl: z.string().url().optional(),
  billingPortalReturnUrl: z.string().url().optional(),
  productName: z.string().optional(),
  productDescription: z.string().optional(),
  oneTimeAmount: z.number().int().positive().optional(),
  currency: z.string().length(3).optional(),
  tiers: z.array(pricingTierSchema).optional(),
  webhookEvents: z.array(z.string()).optional(),
  provision: z
    .object({
      reuseExisting: z.boolean().default(true),
      createWebhook: z.boolean().default(true),
      createPortal: z.boolean().default(true),
    })
    .optional(),
});

export function parseStripeConfig(raw: unknown): StripeAutomationConfig {
  const parsed = stripeConfigSchema.parse(raw);
  return {
    appUrl: parsed.appUrl,
    webhookUrl: parsed.webhookUrl,
    billingPortalReturnUrl: parsed.billingPortalReturnUrl,
    productName: parsed.productName,
    productDescription: parsed.productDescription,
    oneTimeAmount: parsed.oneTimeAmount,
    currency: parsed.currency,
    tiers: parsed.tiers,
    webhookEvents: parsed.webhookEvents,
    provision: parsed.provision,
  };
}

export function resolveAutomationUrls(
  config: StripeAutomationConfig,
  profile: Pick<ProjectProfile, "framework" | "nextRouter">,
  fallbackAppUrl: string
): StripeAutomationConfig {
  const appUrl = config.appUrl ?? fallbackAppUrl;
  const webhookPath = resolveWebhookPath(profile);

  return {
    ...config,
    appUrl,
    webhookUrl: config.webhookUrl ?? `${appUrl}${webhookPath}`,
    billingPortalReturnUrl: config.billingPortalReturnUrl ?? `${appUrl}/account`,
  };
}
