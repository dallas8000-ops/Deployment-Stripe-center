import type { Framework, NextRouter, ProjectProfile } from "../types.js";

export type CodeGenSupport = "full" | "partial" | "minimal" | "none";

export interface FrameworkCapabilities {
  framework: Framework;
  codegen: CodeGenSupport;
  webhookPath: string;
  displayName: string;
  /** Human-readable summary for diagnose UI */
  summary: string;
}

const CAPABILITIES: Record<Framework, Omit<FrameworkCapabilities, "framework">> = {
  nextjs: {
    codegen: "full",
    webhookPath: "/api/stripe/webhook",
    displayName: "Next.js",
    summary: "Full checkout, webhooks, portal, and pricing pages",
  },
  express: {
    codegen: "full",
    webhookPath: "/stripe/webhook",
    displayName: "Express",
    summary: "API routes, static billing pages, webhook handler",
  },
  fastify: {
    codegen: "full",
    webhookPath: "/stripe/webhook",
    displayName: "Fastify",
    summary: "Plugin, static billing pages, webhook and checkout routes",
  },
  remix: {
    codegen: "full",
    webhookPath: "/api/stripe/webhook",
    displayName: "Remix",
    summary: "Resource routes, pricing pages, and portal UI",
  },
  react: {
    codegen: "full",
    webhookPath: "/api/stripe/webhook",
    displayName: "React (SPA)",
    summary: "Pages, components, and dev API server for Stripe",
  },
  nuxt: {
    codegen: "full",
    webhookPath: "/api/stripe/webhook",
    displayName: "Nuxt",
    summary: "Server API routes, Vue pricing pages, and portal UI",
  },
  sveltekit: {
    codegen: "full",
    webhookPath: "/api/stripe/webhook",
    displayName: "SvelteKit",
    summary: "+server.ts API routes and Svelte billing pages",
  },
  django: {
    codegen: "full",
    webhookPath: "/stripe/webhook",
    displayName: "Django",
    summary: "Views, templates, URLs for full billing flow",
  },
  flask: {
    codegen: "full",
    webhookPath: "/stripe/webhook",
    displayName: "Flask",
    summary: "Blueprint, templates, and billing pages",
  },
  rails: {
    codegen: "full",
    webhookPath: "/stripe/webhook",
    displayName: "Rails",
    summary: "Controller, ERB views, and webhook handling",
  },
  laravel: {
    codegen: "full",
    webhookPath: "/stripe/webhook",
    displayName: "Laravel",
    summary: "Controller, Blade views, and webhook handling",
  },
  unknown: {
    codegen: "minimal",
    webhookPath: "/stripe/webhook",
    displayName: "Unknown",
    summary: "Generic Stripe client library files only",
  },
};

export function getFrameworkCapabilities(framework: Framework): FrameworkCapabilities {
  const cap = CAPABILITIES[framework] ?? CAPABILITIES.unknown;
  return { framework, ...cap };
}

export function resolveWebhookPath(profile: Pick<ProjectProfile, "framework" | "nextRouter">): string {
  if (profile.framework === "nextjs" && profile.nextRouter === "pages") {
    return "/api/stripe/webhook";
  }
  return getFrameworkCapabilities(profile.framework).webhookPath;
}

/** Directory prefix for generated lib files */
export function libDir(profile: ProjectProfile): string {
  switch (profile.framework) {
    case "express":
    case "fastify":
      return "src/lib";
    case "remix":
      return "app/lib";
    case "nuxt":
      return "server/utils";
    case "sveltekit":
      return "src/lib";
    default:
      return "lib";
  }
}

export function frameworkRecommendations(profile: ProjectProfile): string[] {
  const recs: string[] = [];
  const cap = getFrameworkCapabilities(profile.framework);

  switch (profile.framework) {
    case "nextjs":
      recs.push("Use Route Handlers (app/api) or Pages API routes for webhooks.");
      recs.push("Keep STRIPE_SECRET_KEY server-side; expose publishable key via NEXT_PUBLIC_*.");
      if (profile.nextRouter === "pages") {
        recs.push("Pages router: disable bodyParser on webhook route for signature verification.");
      }
      break;
    case "express":
      recs.push("Mount POST /stripe/webhook with express.raw() BEFORE express.json() globally.");
      recs.push("Register generated router: app.use('/stripe', stripeRouter) or merge routes.");
      break;
    case "fastify":
      recs.push("Use addContentTypeParser for application/json on webhook route only.");
      recs.push("Register stripePlugin before other JSON parsers.");
      break;
    case "remix":
      recs.push("Use action() in resource routes — never expose secret key to loaders.");
      recs.push("Webhook route must read raw body via request.text() for constructEvent.");
      break;
    case "react":
      recs.push("Generated pages + server/dev-server.ts — proxy /api to port 3001 in Vite.");
      recs.push("Never put STRIPE_SECRET_KEY in the browser bundle.");
      break;
    case "nuxt":
      recs.push("Generated server/api/stripe/* routes — register webhook URL in Stripe Dashboard.");
      recs.push("Add stripe to nuxt.config runtimeConfig if exposing publishable key to client.");
      break;
    case "sveltekit":
      recs.push("Generated src/routes/api/stripe/* +server.ts handlers.");
      recs.push("Use $lib/stripe only in +server.ts or server hooks — never in client components.");
      break;
    case "django":
      recs.push("Include stripe.urls in your root urls.py: path('stripe/', include('stripe.urls')).");
      recs.push("Install stripe: pip install stripe — add to requirements.txt.");
      break;
    case "flask":
      recs.push("Register blueprint: app.register_blueprint(stripe_bp) from stripe_routes.py.");
      recs.push("Use request.data (bytes) for webhook signature verification.");
      break;
    case "rails":
      recs.push("Add routes from docs/STRIPE-RAILS.md — gem 'stripe' required.");
      break;
    case "laravel":
      recs.push("Require routes/stripe.php and composer require stripe/stripe-php.");
      break;
    default:
      recs.push(`Codegen level: ${cap.codegen} — ${cap.summary}`);
  }

  return recs;
}

export function supportsFileDiagnostics(profile: ProjectProfile): boolean {
  const cap = getFrameworkCapabilities(profile.framework);
  return cap.codegen !== "none";
}
