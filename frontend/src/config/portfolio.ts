/** Keep in sync with backend apps/stripe_core/portfolio_catalog.py */

export const MERGED_LEGACY_PROJECT_SLUGS = new Set([
  "api-transfer",
  "api_transfer",
  "elite-fintech-web",
]);

/** Legacy slug → canonical project slug (keep in sync with backend portfolio_catalog.py). */
export const MERGED_INTO_PROJECT_SLUGS: Record<string, string> = {
  "api-transfer": "stripe-installer",
  api_transfer: "stripe-installer",
  "elite-fintech-web": "elite-fintech-systems",
};

/** Portfolio demos — not Stripe billing workspaces (hidden from Projects list). */
export const STRIPE_EXEMPT_PROJECT_SLUGS = new Set([
  "kistie-store",
  "silverfox",
  "blog-2",
  "react-store-catalog",
]);

export const DASHBOARD_HIDDEN_PROJECT_SLUGS = new Set([
  ...MERGED_LEGACY_PROJECT_SLUGS,
  ...STRIPE_EXEMPT_PROJECT_SLUGS,
]);

export function isMergedLegacyProject(slug: string): boolean {
  return MERGED_LEGACY_PROJECT_SLUGS.has(slug);
}

export function canonicalProjectSlug(slug: string): string {
  return MERGED_INTO_PROJECT_SLUGS[slug] ?? slug;
}

export function isStripeExemptProject(slug: string): boolean {
  return STRIPE_EXEMPT_PROJECT_SLUGS.has(slug);
}

export function isDashboardHiddenProject(slug: string): boolean {
  return DASHBOARD_HIDDEN_PROJECT_SLUGS.has(slug);
}

export function filterVisibleProjects<T extends { slug: string }>(projects: T[]): T[] {
  return projects.filter((p) => !isDashboardHiddenProject(p.slug));
}

/** Portfolio storefront demos — hidden from billing list but managed here for Railway deploy. */
export const PORTFOLIO_DEMOS = [
  {
    slug: "silverfox",
    name: "SilverFox",
    productionUrl: "https://silverfox-production.up.railway.app",
    localPath: "C:\\Software Projects\\SilverFox",
    note: "Men's Django SSR — Stripe exempt",
  },
  {
    slug: "kistie-store",
    name: "Kistie Store",
    productionUrl: "https://kistie-store-production.up.railway.app",
    localPath: "C:\\Software Projects\\Kristie-Store",
    note: "Women's Django SSR — Stripe exempt",
  },
  {
    slug: "blog-2",
    name: "Django REST Blog API",
    productionUrl: "https://blog-2-production-72bc.up.railway.app",
    localPath: "",
    note: "Portfolio API — Stripe exempt",
  },
  {
    slug: "react-store-catalog",
    name: "React Store Catalog",
    productionUrl: "https://react-store-catalog-1-production.up.railway.app",
    localPath: "",
    note: "Catalog demo — Stripe exempt",
  },
] as const;
