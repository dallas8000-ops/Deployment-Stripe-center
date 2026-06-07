import Stripe from "stripe";
import type { KeyVerificationResult } from "../types.js";
import { SecretVault } from "../security/vault.js";

export const STRIPE_API_VERSION = "2025-02-24.acacia" as const;
export type { KeyVerificationResult };

export async function getStripeClient(vault: SecretVault): Promise<Stripe> {
  const secretKey = await vault.get("STRIPE_SECRET_KEY");
  if (!secretKey) {
    throw new Error("STRIPE_SECRET_KEY not found in vault.");
  }
  return new Stripe(secretKey, { apiVersion: STRIPE_API_VERSION });
}

export function detectKeyMode(key: string): "test" | "live" | "unknown" {
  if (key.includes("_test_")) return "test";
  if (key.includes("_live_")) return "live";
  return "unknown";
}

export async function verifyApiKeys(vault: SecretVault): Promise<KeyVerificationResult> {
  const secretKey = await vault.get("STRIPE_SECRET_KEY");
  const publishableKey = await vault.get("STRIPE_PUBLISHABLE_KEY");

  const result: KeyVerificationResult = {
    secretKey: {
      valid: false,
      mode: secretKey ? detectKeyMode(secretKey) : "unknown",
      message: "Not configured",
    },
    publishableKey: {
      valid: false,
      mode: publishableKey ? detectKeyMode(publishableKey) : "unknown",
      message: "Not configured",
    },
  };

  if (!secretKey) {
    result.secretKey.message = "STRIPE_SECRET_KEY missing from vault";
    return result;
  }

  if (!/^sk_(test|live)_/.test(secretKey)) {
    result.secretKey.message = "Invalid secret key format (expected sk_test_ or sk_live_)";
    return result;
  }

  try {
    const stripe = new Stripe(secretKey, { apiVersion: STRIPE_API_VERSION });
    const [balance, account] = await Promise.all([
      stripe.balance.retrieve(),
      stripe.accounts.retrieve(),
    ]);
    result.secretKey.valid = true;
    result.secretKey.message = `Valid (${result.secretKey.mode} mode, balance available)`;
    result.accountId = account.id;
    result.accountName = account.business_profile?.name ?? account.settings?.dashboard?.display_name ?? account.id;
    result.country = account.country ?? undefined;
    result.billingEnabled = account.capabilities?.card_payments === "active";
    void balance;
  } catch (err) {
    result.secretKey.message =
      err instanceof Error ? err.message : "Secret key verification failed";
  }

  if (!publishableKey) {
    result.publishableKey.message = "STRIPE_PUBLISHABLE_KEY missing from vault";
    return result;
  }

  if (!/^pk_(test|live)_/.test(publishableKey)) {
    result.publishableKey.message = "Invalid publishable key format (expected pk_test_ or pk_live_)";
    return result;
  }

  if (
    result.secretKey.valid &&
    result.secretKey.mode !== "unknown" &&
    result.publishableKey.mode !== "unknown" &&
    result.secretKey.mode !== result.publishableKey.mode
  ) {
    result.publishableKey.message = `Mode mismatch: secret is ${result.secretKey.mode}, publishable is ${result.publishableKey.mode}`;
    return result;
  }

  result.publishableKey.valid = true;
  result.publishableKey.message = `Valid (${result.publishableKey.mode} mode)`;
  return result;
}
