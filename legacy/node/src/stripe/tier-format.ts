import type { StripeManifest } from "../types.js";

export function tierKey(name: string): string {
  return name.toLowerCase().replace(/\s+/g, "_");
}

export function formatAmount(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

export interface UiApiPaths {
  checkout: string;
  portal: string;
  pricing: string;
  success: string;
  account: string;
}

export function apiPathsForCheckout(framework: string): UiApiPaths {
  if (
    framework === "nextjs" ||
    framework === "remix" ||
    framework === "nuxt" ||
    framework === "sveltekit" ||
    framework === "react"
  ) {
    return {
      checkout: "/api/stripe/checkout",
      portal: "/api/stripe/portal",
      pricing: "/pricing",
      success: "/success",
      account: "/account",
    };
  }

  if (framework === "express" || framework === "fastify") {
    return {
      checkout: "/stripe/checkout",
      portal: "/stripe/portal",
      pricing: "/pricing.html",
      success: "/success.html",
      account: "/account.html",
    };
  }

  return {
    checkout: "/stripe/checkout",
    portal: "/stripe/portal",
    pricing: "/stripe/pricing",
    success: "/stripe/success",
    account: "/stripe/account",
  };
}

export interface TierCardData {
  tier: string;
  key: string;
  priceId: string;
  label: string;
  trialDays?: number;
  features: string[];
}

export function tierCardsFromManifest(manifest?: StripeManifest | null): TierCardData[] {
  return (manifest?.prices ?? []).map((p) => ({
    tier: p.tier,
    key: tierKey(p.tier),
    priceId: p.id,
    label: formatAmount(p.amount, p.currency) + (p.interval ? `/${p.interval}` : ""),
    trialDays: p.trialDays,
    features: p.features ?? [],
  }));
}
