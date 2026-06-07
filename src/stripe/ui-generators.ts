import type { Framework } from "../types.js";
import type { StripeManifest } from "../types.js";
import {
  apiPathsForCheckout,
  tierCardsFromManifest,
  type UiApiPaths,
} from "./tier-format.js";
import { sessionInfoApiPath, vanillaSuccessSessionScript } from "./session-routes.js";

export function generateUiFiles(
  framework: Framework,
  manifest?: StripeManifest | null
): Record<string, string> {
  const paths = apiPathsForCheckout(framework);
  const sessionPath = sessionInfoApiPath(framework);
  switch (framework) {
    case "express":
    case "fastify":
      return vanillaPublicUi(paths, manifest, sessionPath);
    case "remix":
      return remixUi(paths, manifest, sessionPath);
    case "nuxt":
      return nuxtUi(paths, manifest, sessionPath);
    case "sveltekit":
      return sveltekitUi(paths, manifest, sessionPath);
    case "react":
      return reactUi(paths, manifest, sessionPath);
    case "django":
      return djangoUi(paths, manifest, sessionPath);
    case "flask":
      return flaskUi(paths, manifest, sessionPath);
    case "rails":
      return railsUi(paths, manifest, sessionPath);
    case "laravel":
      return laravelUi(paths, manifest, sessionPath);
    default:
      return {};
  }
}

function vanillaPublicUi(
  paths: UiApiPaths,
  manifest?: StripeManifest | null,
  sessionPath = "/stripe/session"
): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  const cards = tiers
    .map(
      (t) => `    <div class="card">
      <h2>${t.tier}</h2>
      <p class="price">${t.label}</p>
      ${t.trialDays ? `<p class="trial">${t.trialDays}-day free trial</p>` : ""}
      ${t.features.length ? `<ul>${t.features.map((f) => `<li>${f}</li>`).join("")}</ul>` : ""}
      <button data-price-id="${t.priceId}">Subscribe</button>
    </div>`
    )
    .join("\n");

  return {
    "public/pricing.html": `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pricing</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; }
    h1 { text-align: center; }
    .grid { display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); margin-top: 2rem; }
    .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; }
    .price { font-size: 1.75rem; font-weight: bold; }
    .trial { color: #059669; font-size: 0.875rem; }
    button { margin-top: 1rem; width: 100%; padding: 0.5rem 1rem; background: #111; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
    button:disabled { opacity: 0.5; }
    .error { color: #dc2626; font-size: 0.875rem; margin-top: 0.5rem; }
  </style>
</head>
<body>
  <h1>Choose your plan</h1>
  <p style="text-align:center;color:#6b7280">Simple, transparent pricing</p>
  <div class="grid">
${cards || "    <p>Run stripe-installer run --provision to create tiers.</p>"}
  </div>
  <script>
    document.querySelectorAll("[data-price-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        const err = btn.parentElement.querySelector(".error") || document.createElement("p");
        err.className = "error";
        try {
          const res = await fetch("${paths.checkout}", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ priceId: btn.dataset.priceId }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || "Checkout failed");
          if (data.url) window.location.href = data.url;
        } catch (e) {
          err.textContent = e.message;
          btn.parentElement.appendChild(err);
          btn.disabled = false;
        }
      });
    });
  </script>
</body>
</html>
`,
    "public/success.html": `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Payment successful</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 480px; margin: 4rem auto; text-align: center; padding: 1rem; }
    h1 { color: #059669; }
    a { display: inline-block; margin-top: 2rem; padding: 0.5rem 1.5rem; background: #111; color: #fff; text-decoration: none; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>Payment successful</h1>
  <p>Thank you for your purchase.</p>
  <p id="session" style="font-size:0.75rem;color:#9ca3af"></p>
  <a href="${paths.account}">Go to account</a>
  ${vanillaSuccessSessionScript(sessionPath)}
</body>
</html>
`,
    "public/account.html": `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Account</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 480px; margin: 2rem auto; padding: 1rem; }
    button { margin-top: 1rem; padding: 0.5rem 1rem; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; cursor: pointer; }
  </style>
</head>
<body>
  <h1>Account</h1>
  <p>Manage your subscription and billing.</p>
  <p id="msg"></p>
  <button id="portal" style="display:none">Manage subscription</button>
  <script>
    const customerId = localStorage.getItem("stripe_customer_id");
    const msg = document.getElementById("msg");
    const btn = document.getElementById("portal");
    if (!customerId) {
      msg.textContent = "No Stripe customer linked. Complete checkout first.";
    } else {
      btn.style.display = "inline-block";
      btn.onclick = async () => {
        btn.disabled = true;
        const res = await fetch("${paths.portal}", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ customerId }),
        });
        const data = await res.json();
        if (data.url) window.location.href = data.url;
        btn.disabled = false;
      };
    }
  </script>
</body>
</html>
`,
    "docs/STRIPE-UI.md": `# Static billing pages

Serve \`public/\` with your static middleware:

\`\`\`javascript
app.use(express.static("public"));
\`\`\`

Pages: ${paths.pricing}, ${paths.success}, ${paths.account}
`,
  };
}

function reactCheckoutButton(paths: UiApiPaths): string {
  return `"use client";

import { useState } from "react";

interface CheckoutButtonProps {
  priceId: string;
  tier?: string;
  label?: string;
  className?: string;
}

export function CheckoutButton({ priceId, tier, label, className }: CheckoutButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCheckout() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("${paths.checkout}", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ priceId, tier }),
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
      <button type="button" onClick={handleCheckout} disabled={loading} className={className}>
        {loading ? "Loading..." : (label ?? "Subscribe")}
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
`;
}

function reactManageButton(paths: UiApiPaths): string {
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
      const res = await fetch("${paths.portal}", {
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
    <button type="button" onClick={openPortal} disabled={loading} className={className}>
      {loading ? "Loading..." : (label ?? "Manage subscription")}
    </button>
  );
}
`;
}

function reactPricingPage(tiers: ReturnType<typeof tierCardsFromManifest>, componentImport: string): string {
  const cards = tiers
    .map(
      (t) => `        <div className="flex flex-col rounded-xl border p-6 shadow-sm">
          <h2 className="text-xl font-semibold">${t.tier}</h2>
          <p className="mt-2 text-3xl font-bold">${t.label}</p>
          ${t.trialDays ? `<p className="text-sm text-green-600">${t.trialDays}-day free trial</p>` : ""}
          <CheckoutButton priceId="${t.priceId}" tier="${t.key}" className="mt-6 rounded-lg bg-black px-4 py-2 text-white disabled:opacity-50" />
        </div>`
    )
    .join("\n");

  return `import { CheckoutButton } from "${componentImport}";

export default function PricingPage() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-16">
      <h1 className="text-center text-4xl font-bold">Choose your plan</h1>
      <p className="mt-2 text-center text-gray-600">Simple, transparent pricing</p>
      <div className="mt-12 grid gap-8 md:grid-cols-${Math.min(Math.max(tiers.length, 1), 3)}">
${cards || `        <p className="col-span-full text-center">Run stripe-installer run --provision to create tiers.</p>`}
      </div>
    </main>
  );
}
`;
}

function remixUi(paths: UiApiPaths, manifest?: StripeManifest | null, sessionPath = "/api/stripe/session"): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  return {
    "app/components/CheckoutButton.tsx": reactCheckoutButton(paths),
    "app/components/ManageSubscriptionButton.tsx": reactManageButton(paths),
    "app/routes/pricing.tsx": reactPricingPage(tiers, "~/components/CheckoutButton"),
    "app/routes/success.tsx": `import { useEffect } from "react";

export default function SuccessPage() {
  useEffect(() => {
    const sessionId = new URLSearchParams(window.location.search).get("session_id");
    if (!sessionId) return;
    fetch("${sessionPath}", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.customerId) localStorage.setItem("stripe_customer_id", data.customerId);
      })
      .catch(() => undefined);
  }, []);

  return (
    <main className="mx-auto max-w-lg px-4 py-24 text-center">
      <h1 className="text-3xl font-bold text-green-600">Payment successful</h1>
      <p className="mt-4 text-gray-600">Thank you for your purchase.</p>
      <a href="${paths.account}" className="mt-8 inline-block rounded-lg bg-black px-6 py-2 text-white">
        Go to account
      </a>
    </main>
  );
}
`,
    "app/routes/account.tsx": `import { ManageSubscriptionButton } from "~/components/ManageSubscriptionButton";

export default function AccountPage() {
  const customerId = typeof window !== "undefined" ? localStorage.getItem("stripe_customer_id") : null;
  return (
    <main className="mx-auto max-w-lg px-4 py-16">
      <h1 className="text-2xl font-bold">Account</h1>
      <p className="mt-2 text-gray-600">Manage your subscription and billing.</p>
      {customerId ? (
        <ManageSubscriptionButton customerId={customerId} className="mt-6 rounded-lg border px-4 py-2 hover:bg-gray-50" />
      ) : (
        <p className="mt-6 text-sm text-gray-500">No Stripe customer linked. Complete checkout first.</p>
      )}
    </main>
  );
}
`,
  };
}

function reactUi(paths: UiApiPaths, manifest?: StripeManifest | null, sessionPath = "/api/stripe/session"): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  return {
    "src/components/CheckoutButton.tsx": reactCheckoutButton(paths),
    "src/components/ManageSubscriptionButton.tsx": reactManageButton(paths),
    "src/pages/Pricing.tsx": reactPricingPage(tiers, "../components/CheckoutButton"),
    "src/pages/Success.tsx": `import { useEffect } from "react";

export default function SuccessPage() {
  useEffect(() => {
    const sessionId = new URLSearchParams(window.location.search).get("session_id");
    if (!sessionId) return;
    fetch("${sessionPath}", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.customerId) localStorage.setItem("stripe_customer_id", data.customerId);
      })
      .catch(() => undefined);
  }, []);

  return (
    <main style={{ maxWidth: 480, margin: "4rem auto", textAlign: "center", padding: "1rem" }}>
      <h1 style={{ color: "#059669" }}>Payment successful</h1>
      <p>Thank you for your purchase.</p>
      <a href="${paths.account}" style={{ display: "inline-block", marginTop: "2rem", padding: "0.5rem 1.5rem", background: "#111", color: "#fff", borderRadius: 8, textDecoration: "none" }}>
        Go to account
      </a>
    </main>
  );
}
`,
    "src/pages/Account.tsx": `import { ManageSubscriptionButton } from "../components/ManageSubscriptionButton";

export default function AccountPage() {
  const customerId = typeof window !== "undefined" ? localStorage.getItem("stripe_customer_id") : null;
  return (
    <main style={{ maxWidth: 480, margin: "2rem auto", padding: "1rem" }}>
      <h1>Account</h1>
      <p>Manage your subscription and billing.</p>
      {customerId ? (
        <ManageSubscriptionButton customerId={customerId} />
      ) : (
        <p>No Stripe customer linked. Complete checkout first.</p>
      )}
    </main>
  );
}
`,
    "server/dev-server.ts": generateReactDevServer(paths),
    "docs/STRIPE-REACT.md": `# React + Stripe dev server

1. \`npm install express stripe\`
2. Run API: \`npx tsx server/dev-server.ts\`
3. Proxy Vite \`/api\` → \`http://localhost:3001\` in \`vite.config.ts\`
4. Routes: ${paths.pricing}, ${paths.success}, ${paths.account}
`,
  };
}

function generateReactDevServer(paths: UiApiPaths): string {
  return `import express from "express";
import Stripe from "stripe";

const app = express();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: "2025-02-24.acacia" });
const APP_URL = process.env.APP_URL ?? "http://localhost:5173";

app.post("${paths.checkout}", express.json(), async (req, res) => {
  const { priceId, customerEmail } = req.body;
  if (!priceId) return res.status(400).json({ error: "priceId required" });
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer_email: customerEmail,
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: \`\${APP_URL}/success?session_id={CHECKOUT_SESSION_ID}\`,
    cancel_url: \`\${APP_URL}/pricing\`,
  });
  res.json({ url: session.url });
});

app.post("${paths.portal}", express.json(), async (req, res) => {
  const { customerId } = req.body;
  if (!customerId) return res.status(400).json({ error: "customerId required" });
  const session = await stripe.billingPortal.sessions.create({
    customer: customerId,
    return_url: \`\${APP_URL}/account\`,
  });
  res.json({ url: session.url });
});

app.post("/api/stripe/webhook", express.raw({ type: "application/json" }), async (req, res) => {
  const sig = req.headers["stripe-signature"] as string;
  try {
    const event = stripe.webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET!);
    console.log("[stripe]", event.type);
    res.json({ received: true });
  } catch (err) {
    res.status(400).send(\`Webhook Error: \${(err as Error).message}\`);
  }
});

app.listen(3001, () => console.log("Stripe dev API on http://localhost:3001"));
`;
}

function nuxtUi(paths: UiApiPaths, manifest?: StripeManifest | null, sessionPath = "/api/stripe/session"): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  const cards = tiers
    .map(
      (t) => `      <div class="card">
        <h2>${t.tier}</h2>
        <p class="price">${t.label}</p>
        <CheckoutButton price-id="${t.priceId}" />
      </div>`
    )
    .join("\n");

  return {
    "components/CheckoutButton.vue": `<script setup lang="ts">
const props = defineProps<{ priceId: string; label?: string }>();
const loading = ref(false);
const error = ref<string | null>(null);

async function checkout() {
  loading.value = true;
  error.value = null;
  try {
    const data = await $fetch<{ url?: string; error?: string }>("${paths.checkout}", {
      method: "POST",
      body: { priceId: props.priceId },
    });
    if (data.url) window.location.href = data.url;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Checkout failed";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div>
    <button type="button" :disabled="loading" @click="checkout">{{ loading ? "Loading..." : (label ?? "Subscribe") }}</button>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
button { margin-top: 1rem; padding: 0.5rem 1rem; background: #111; color: #fff; border: none; border-radius: 8px; }
.error { color: #dc2626; font-size: 0.875rem; }
</style>
`,
    "components/ManageSubscriptionButton.vue": `<script setup lang="ts">
const props = defineProps<{ customerId: string }>();
const loading = ref(false);

async function openPortal() {
  loading.value = true;
  try {
    const data = await $fetch<{ url?: string }>("${paths.portal}", {
      method: "POST",
      body: { customerId: props.customerId },
    });
    if (data.url) window.location.href = data.url;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <button type="button" :disabled="loading" @click="openPortal">
    {{ loading ? "Loading..." : "Manage subscription" }}
  </button>
</template>
`,
    "pages/pricing.vue": `<template>
  <main class="page">
    <h1>Choose your plan</h1>
    <div class="grid">
${cards || "      <p>Run stripe-installer run --provision to create tiers.</p>"}
    </div>
  </main>
</template>

<style scoped>
.page { max-width: 960px; margin: 0 auto; padding: 2rem; }
.grid { display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); margin-top: 2rem; }
.card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; }
.price { font-size: 1.75rem; font-weight: bold; }
</style>
`,
    "pages/success.vue": `<script setup lang="ts">
onMounted(async () => {
  const sessionId = new URLSearchParams(window.location.search).get("session_id");
  if (!sessionId) return;
  try {
    const data = await $fetch<{ customerId?: string }>("${sessionPath}", {
      method: "POST",
      body: { sessionId },
    });
    if (data.customerId) localStorage.setItem("stripe_customer_id", data.customerId);
  } catch { /* ignore */ }
});
</script>

<template>
  <main class="page">
    <h1 class="ok">Payment successful</h1>
    <p>Thank you for your purchase.</p>
    <NuxtLink to="${paths.account}">Go to account</NuxtLink>
  </main>
</template>

<style scoped>
.page { max-width: 480px; margin: 4rem auto; text-align: center; }
.ok { color: #059669; }
</style>
`,
    "pages/account.vue": `<script setup lang="ts">
const customerId = ref<string | null>(null);
onMounted(() => {
  customerId.value = localStorage.getItem("stripe_customer_id");
});
</script>

<template>
  <main class="page">
    <h1>Account</h1>
    <p>Manage your subscription and billing.</p>
    <ManageSubscriptionButton v-if="customerId" :customer-id="customerId" />
    <p v-else>No Stripe customer linked. Complete checkout first.</p>
  </main>
</template>

<style scoped>
.page { max-width: 480px; margin: 2rem auto; padding: 1rem; }
</style>
`,
  };
}

function sveltekitUi(paths: UiApiPaths, manifest?: StripeManifest | null, sessionPath = "/api/stripe/session"): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  const cards = tiers
    .map(
      (t) => `    <div class="card">
      <h2>${t.tier}</h2>
      <p class="price">${t.label}</p>
      <CheckoutButton priceId="${t.priceId}" />
    </div>`
    )
    .join("\n");

  return {
    "src/lib/components/CheckoutButton.svelte": `<script lang="ts">
  export let priceId: string;
  export let label = "Subscribe";
  let loading = false;
  let error: string | null = null;

  async function checkout() {
    loading = true;
    error = null;
    try {
      const res = await fetch("${paths.checkout}", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ priceId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Checkout failed");
      if (data.url) window.location.href = data.url;
    } catch (e) {
      error = e instanceof Error ? e.message : "Checkout failed";
    } finally {
      loading = false;
    }
  }
</script>

<button type="button" disabled={loading} on:click={checkout}>{loading ? "Loading..." : label}</button>
{#if error}<p class="error">{error}</p>{/if}

<style>
  button { margin-top: 1rem; padding: 0.5rem 1rem; background: #111; color: #fff; border: none; border-radius: 8px; }
  .error { color: #dc2626; font-size: 0.875rem; }
</style>
`,
    "src/lib/components/ManageSubscriptionButton.svelte": `<script lang="ts">
  export let customerId: string;
  let loading = false;

  async function openPortal() {
    loading = true;
    try {
      const res = await fetch("${paths.portal}", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ customerId }),
      });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } finally {
      loading = false;
    }
  }
</script>

<button type="button" disabled={loading} on:click={openPortal}>
  {loading ? "Loading..." : "Manage subscription"}
</button>
`,
    "src/routes/pricing/+page.svelte": `<script>
  import CheckoutButton from "$lib/components/CheckoutButton.svelte";
</script>

<main class="page">
  <h1>Choose your plan</h1>
  <div class="grid">
${cards || "    <p>Run stripe-installer run --provision to create tiers.</p>"}
  </div>
</main>

<style>
  .page { max-width: 960px; margin: 0 auto; padding: 2rem; }
  .grid { display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); margin-top: 2rem; }
  .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; }
  .price { font-size: 1.75rem; font-weight: bold; }
</style>
`,
    "src/routes/success/+page.svelte": `<script lang="ts">
  import { onMount } from "svelte";
  onMount(async () => {
    const sessionId = new URLSearchParams(window.location.search).get("session_id");
    if (!sessionId) return;
    try {
      const res = await fetch("${sessionPath}", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId }),
      });
      const data = await res.json();
      if (data.customerId) localStorage.setItem("stripe_customer_id", data.customerId);
    } catch { /* ignore */ }
  });
</script>

<main class="page">
  <h1 class="ok">Payment successful</h1>
  <p>Thank you for your purchase.</p>
  <a href="${paths.account}">Go to account</a>
</main>

<style>
  .page { max-width: 480px; margin: 4rem auto; text-align: center; }
  .ok { color: #059669; }
</style>
`,
    "src/routes/account/+page.svelte": `<script lang="ts">
  import { onMount } from "svelte";
  import ManageSubscriptionButton from "$lib/components/ManageSubscriptionButton.svelte";
  let customerId: string | null = null;
  onMount(() => {
    customerId = localStorage.getItem("stripe_customer_id");
  });
</script>

<main class="page">
  <h1>Account</h1>
  <p>Manage your subscription and billing.</p>
  {#if customerId}
    <ManageSubscriptionButton {customerId} />
  {:else}
    <p>No Stripe customer linked. Complete checkout first.</p>
  {/if}
</main>

<style>
  .page { max-width: 480px; margin: 2rem auto; padding: 1rem; }
</style>
`,
  };
}

function pythonPricingTemplate(tiers: ReturnType<typeof tierCardsFromManifest>, checkoutPath: string): string {
  const cards = tiers
    .map(
      (t) => `  <div class="card">
    <h2>${t.tier}</h2>
    <p class="price">${t.label}</p>
    <button data-price-id="${t.priceId}">Subscribe</button>
  </div>`
    )
    .join("\n");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Pricing</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; }
    .grid { display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); margin-top: 2rem; }
    .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; }
    .price { font-size: 1.75rem; font-weight: bold; }
    button { margin-top: 1rem; width: 100%; padding: 0.5rem; background: #111; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
  </style>
</head>
<body>
  <h1>Choose your plan</h1>
  <div class="grid">
${cards || "    <p>Run stripe-installer run --provision to create tiers.</p>"}
  </div>
  <script>
    document.querySelectorAll("[data-price-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        const res = await fetch("${checkoutPath}", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ priceId: btn.dataset.priceId }),
        });
        const data = await res.json();
        if (data.url) window.location.href = data.url;
        btn.disabled = false;
      });
    });
  </script>
</body>
</html>
`;
}

function djangoUi(paths: UiApiPaths, manifest?: StripeManifest | null, sessionPath = "/stripe/session"): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  return {
    "stripe/templates/stripe/pricing.html": pythonPricingTemplate(tiers, paths.checkout),
    "stripe/templates/stripe/success.html": `<!DOCTYPE html>
<html><head><title>Success</title></head>
<body style="font-family:system-ui;text-align:center;margin:4rem auto">
  <h1 style="color:#059669">Payment successful</h1>
  <p>Thank you for your purchase.</p>
  <a href="${paths.account}">Go to account</a>
  ${vanillaSuccessSessionScript(sessionPath)}
</body></html>
`,
    "stripe/templates/stripe/account.html": `<!DOCTYPE html>
<html><head><title>Account</title></head>
<body style="font-family:system-ui;max-width:480px;margin:2rem auto">
  <h1>Account</h1>
  <p>Manage your subscription and billing.</p>
  <button id="portal" style="display:none">Manage subscription</button>
  <p id="msg"></p>
  <script>
    const customerId = localStorage.getItem("stripe_customer_id");
    if (!customerId) document.getElementById("msg").textContent = "No Stripe customer linked.";
    else {
      const btn = document.getElementById("portal");
      btn.style.display = "inline-block";
      btn.onclick = async () => {
        const res = await fetch("${paths.portal}", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customerId }) });
        const data = await res.json();
        if (data.url) window.location.href = data.url;
      };
    }
  </script>
</body></html>
`,
  };
}

function flaskUi(paths: UiApiPaths, manifest?: StripeManifest | null, sessionPath = "/stripe/session"): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  return {
    "templates/stripe/pricing.html": pythonPricingTemplate(tiers, paths.checkout),
    "templates/stripe/success.html": `<!DOCTYPE html>
<html><head><title>Success</title></head>
<body style="font-family:system-ui;text-align:center;margin:4rem auto">
  <h1 style="color:#059669">Payment successful</h1>
  <a href="${paths.account}">Go to account</a>
  ${vanillaSuccessSessionScript(sessionPath)}
</body></html>
`,
    "templates/stripe/account.html": `<!DOCTYPE html>
<html><head><title>Account</title></head>
<body style="font-family:system-ui;max-width:480px;margin:2rem auto">
  <h1>Account</h1>
  <button id="portal" style="display:none">Manage subscription</button>
  <script>
    const customerId = localStorage.getItem("stripe_customer_id");
    if (customerId) {
      document.getElementById("portal").style.display = "inline-block";
      document.getElementById("portal").onclick = async () => {
        const res = await fetch("${paths.portal}", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customerId }) });
        const data = await res.json();
        if (data.url) location.href = data.url;
      };
    }
  </script>
</body></html>
`,
  };
}

function railsUi(paths: UiApiPaths, manifest?: StripeManifest | null, sessionPath = "/stripe/session"): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  return {
    "app/views/stripe/pricing.html.erb": pythonPricingTemplate(tiers, paths.checkout),
    "app/views/stripe/success.html.erb": `<main style="text-align:center;margin:4rem auto;font-family:system-ui">
  <h1 style="color:#059669">Payment successful</h1>
  <a href="${paths.account}">Go to account</a>
  ${vanillaSuccessSessionScript(sessionPath)}
</main>
`,
    "app/views/stripe/account.html.erb": `<main style="max-width:480px;margin:2rem auto;font-family:system-ui">
  <h1>Account</h1>
  <button id="portal" style="display:none">Manage subscription</button>
  <script>
    const customerId = localStorage.getItem("stripe_customer_id");
    if (customerId) {
      document.getElementById("portal").style.display = "inline-block";
      document.getElementById("portal").onclick = async () => {
        const res = await fetch("${paths.portal}", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customerId }) });
        const data = await res.json();
        if (data.url) location.href = data.url;
      };
    }
  </script>
</main>
`,
  };
}

function laravelUi(paths: UiApiPaths, manifest?: StripeManifest | null, sessionPath = "/stripe/session"): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  return {
    "resources/views/stripe/pricing.blade.php": pythonPricingTemplate(tiers, paths.checkout),
    "resources/views/stripe/success.blade.php": `<main style="text-align:center;margin:4rem auto;font-family:system-ui">
  <h1 style="color:#059669">Payment successful</h1>
  <a href="${paths.account}">Go to account</a>
  ${vanillaSuccessSessionScript(sessionPath)}
</main>
`,
    "resources/views/stripe/account.blade.php": `<main style="max-width:480px;margin:2rem auto;font-family:system-ui">
  <h1>Account</h1>
  <button id="portal" style="display:none">Manage subscription</button>
  <script>
    const customerId = localStorage.getItem("stripe_customer_id");
    if (customerId) {
      document.getElementById("portal").style.display = "inline-block";
      document.getElementById("portal").onclick = async () => {
        const res = await fetch("${paths.portal}", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customerId }) });
        const data = await res.json();
        if (data.url) location.href = data.url;
      };
    }
  </script>
</main>
`,
  };
}

export function djangoPageViews(): string {
  return `from django.shortcuts import render


def pricing(request):
    return render(request, "stripe/pricing.html")


def success(request):
    return render(request, "stripe/success.html")


def account(request):
    return render(request, "stripe/account.html")
`;
}

export function djangoUrlsWithPages(): string {
  return `from django.urls import path

from . import views

urlpatterns = [
    path("webhook", views.webhook, name="stripe-webhook"),
    path("checkout", views.checkout, name="stripe-checkout"),
    path("portal", views.portal, name="stripe-portal"),
    path("session", views.session_info, name="stripe-session"),
    path("pricing", views.pricing, name="stripe-pricing"),
    path("success", views.success, name="stripe-success"),
    path("account", views.account, name="stripe-account"),
]
`;
}

export function djangoSessionView(): string {
  return `
@csrf_exempt
@require_POST
def session_info(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    session_id = data.get("sessionId")
    if not session_id:
        return JsonResponse({"error": "sessionId required"}, status=400)
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        return JsonResponse({"error": str(e)}, status=400)
    customer_id = session.customer if isinstance(session.customer, str) else getattr(session.customer, "id", None)
    return JsonResponse({
        "customerId": customer_id,
        "email": session.customer_email,
        "status": session.status,
    })
`;
}

export function flaskPageRoutes(): string {
  return `
@stripe_bp.route("/session", methods=["POST"])
def session_info():
    data = request.get_json(silent=True) or {}
    session_id = data.get("sessionId")
    if not session_id:
        return jsonify({"error": "sessionId required"}), 400
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e)}), 400
    customer_id = session.customer if isinstance(session.customer, str) else getattr(session.customer, "id", None)
    return jsonify({"customerId": customer_id, "email": session.customer_email, "status": session.status})


@stripe_bp.route("/pricing")
def pricing_page():
    return render_template("stripe/pricing.html")


@stripe_bp.route("/success")
def success_page():
    return render_template("stripe/success.html")


@stripe_bp.route("/account")
def account_page():
    return render_template("stripe/account.html")
`;
}
