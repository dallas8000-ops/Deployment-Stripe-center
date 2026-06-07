import type { PricingTier } from "../types.js";

/** Default SaaS pricing tiers used when --provision runs without a custom config */
export const DEFAULT_SAAS_TIERS: PricingTier[] = [
  {
    name: "Starter",
    description: "Essential features for individuals",
    amount: 900,
    currency: "usd",
    interval: "month",
    trialDays: 14,
    features: ["Core features", "Email support", "1 user"],
  },
  {
    name: "Pro",
    description: "Advanced features for growing teams",
    amount: 2900,
    currency: "usd",
    interval: "month",
    trialDays: 14,
    features: ["Everything in Starter", "Priority support", "Up to 10 users", "Analytics"],
  },
  {
    name: "Enterprise",
    description: "Full access with priority support",
    amount: 99000,
    currency: "usd",
    interval: "year",
    features: ["Everything in Pro", "Dedicated support", "Unlimited users", "SLA"],
  },
];
