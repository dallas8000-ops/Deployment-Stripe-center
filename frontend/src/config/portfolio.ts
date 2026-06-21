/** Keep in sync with backend apps/stripe_installer/portfolio_catalog.py */

export const MERGED_LEGACY_PROJECT_SLUGS = new Set(["api-transfer", "api_transfer"]);

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

export function isStripeExemptProject(slug: string): boolean {
  return STRIPE_EXEMPT_PROJECT_SLUGS.has(slug);
}

export function isDashboardHiddenProject(slug: string): boolean {
  return DASHBOARD_HIDDEN_PROJECT_SLUGS.has(slug);
}

export function filterVisibleProjects<T extends { slug: string }>(projects: T[]): T[] {
  return projects.filter((p) => !isDashboardHiddenProject(p.slug));
}
