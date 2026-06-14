export type Framework =
  | "nextjs"
  | "react"
  | "express"
  | "fastify"
  | "remix"
  | "nuxt"
  | "sveltekit"
  | "django"
  | "flask"
  | "rails"
  | "laravel"
  | "unknown";

export type Language = "typescript" | "javascript" | "python" | "ruby" | "php" | "unknown";

export type StripeFeature =
  | "checkout"
  | "subscriptions"
  | "connect"
  | "billing-portal"
  | "webhooks"
  | "payment-intents"
  | "customer-portal"
  | "invoicing";

export interface DetectedSecret {
  key: string;
  file: string;
  line?: number;
  /** Always a redacted placeholder — never the real value */
  placeholder: string;
}

export type NextRouter = "app" | "pages" | "unknown";

export interface ProjectProfile {
  rootPath: string;
  name: string;
  framework: Framework;
  language: Language;
  nextRouter?: NextRouter;
  hasPackageJson: boolean;
  hasEnvFile: boolean;
  envFiles: string[];
  dependencies: string[];
  devDependencies: string[];
  detectedSecrets: DetectedSecret[];
  suggestedFeatures: StripeFeature[];
  existingStripeCode: boolean;
  serverRuntime: "node" | "edge" | "python" | "ruby" | "php" | "unknown";
  recommendations: string[];
}

export interface StripeSetupPlan {
  features: StripeFeature[];
  envVars: { key: string; description: string; required: boolean }[];
  packagesToInstall: string[];
  filesToCreate: { path: string; purpose: string }[];
  filesToModify: { path: string; purpose: string }[];
  webhookPath?: string;
  notes: string[];
}

export interface VaultEntry {
  key: string;
  encryptedValue: string;
  iv: string;
  authTag: string;
  createdAt: string;
  updatedAt: string;
}

export interface SanitizedContext {
  profile: Omit<ProjectProfile, "detectedSecrets"> & {
    secretKeys: string[];
    secretCount: number;
  };
  plan: StripeSetupPlan;
  /** Safe for AI — no raw secrets */
  promptContext: string;
}

export interface PricingTier {
  name: string;
  description?: string;
  /** Amount in cents */
  amount: number;
  currency: string;
  interval?: "month" | "year";
  trialDays?: number;
  /** Display-only feature list for pricing page */
  features?: string[];
}

export interface StripeAutomationConfig {
  productName?: string;
  productDescription?: string;
  oneTimeAmount?: number;
  currency?: string;
  tiers?: PricingTier[];
  webhookUrl?: string;
  webhookEvents?: string[];
  billingPortalReturnUrl?: string;
  appUrl?: string;
  provision?: {
    reuseExisting?: boolean;
    createWebhook?: boolean;
    createPortal?: boolean;
  };
}

export interface KeyVerificationResult {
  secretKey: { valid: boolean; mode: "test" | "live" | "unknown"; message: string };
  publishableKey: { valid: boolean; mode: "test" | "live" | "unknown"; message: string };
  accountId?: string;
  accountName?: string;
  billingEnabled?: boolean;
  country?: string;
}

export interface StripeAutomationResult {
  verified: KeyVerificationResult;
  products: { id: string; name: string; reused?: boolean }[];
  prices: {
    id: string;
    tier: string;
    amount: number;
    currency: string;
    interval?: string;
    trialDays?: number;
    reused?: boolean;
  }[];
  webhookEndpoint?: { id: string; url: string; reused?: boolean };
  billingPortalConfig?: { id: string; reused?: boolean };
  webhookSecretStored?: boolean;
  warnings: string[];
}

export interface StripeManifest {
  createdAt: string;
  updatedAt: string;
  accountId?: string;
  products: { id: string; name: string }[];
  prices: {
    id: string;
    tier: string;
    amount: number;
    currency: string;
    interval?: string;
    trialDays?: number;
    features?: string[];
  }[];
  webhookEndpoint?: { id: string; url: string };
  billingPortalConfig?: { id: string };
  appUrl?: string;
  framework?: string;
  nextRouter?: NextRouter;
}

export type DeployPlatform = "vercel" | "railway" | "fly" | "docker" | "unknown";

export type PostgresProvider = "neon" | "supabase" | "railway" | "self-hosted" | "unknown";

export interface DeployConfig {
  domain?: string;
  productionUrl?: string;
  platform?: DeployPlatform;
  postgres?: {
    provider?: PostgresProvider;
    connectionEnvVar?: string;
    /** Auto-provision via provider API (neon | supabase) */
    autoProvision?: boolean;
    region?: string;
    projectName?: string;
  };
  monitoring?: {
    healthCheck?: boolean;
    sentry?: boolean;
  };
  backup?: {
    enabled?: boolean;
    retentionDays?: number;
  };
  ssl?: {
    auto?: boolean;
  };
}

export type ReadinessStatus = "pass" | "warn" | "fail";

export interface ReadinessCheck {
  id: string;
  category: "stripe" | "database" | "domain" | "ssl" | "security" | "monitoring" | "backup" | "deploy";
  name: string;
  status: ReadinessStatus;
  message: string;
  fix?: string;
}

export interface DeployResult {
  platform: DeployPlatform;
  readiness: ReadinessCheck[];
  readinessScore: number;
  filesGenerated: string[];
  postgresConnected?: boolean;
  postgresProvisioned?: PostgresProvisionResult;
  productionUrl?: string;
  nextSteps: string[];
  pushResult?: { success: boolean; message: string };
}

export interface DeployManifest {
  deployedAt: string;
  platform: DeployPlatform;
  productionUrl?: string;
  domain?: string;
  postgresProvider?: PostgresProvider;
  readinessScore: number;
}

export type StripeIssueSeverity = "error" | "warning" | "info";

export type StripeIssueCategory =
  | "credentials"
  | "packages"
  | "files"
  | "webhooks"
  | "catalog"
  | "security"
  | "config";

export type StripeFixAction =
  | "import-env"
  | "sync-env"
  | "sync-public-key"
  | "generate-files"
  | "provision-stripe"
  | "fix-gitignore"
  | "create-stripe-config";

export interface StripeIssue {
  id: string;
  category: StripeIssueCategory;
  severity: StripeIssueSeverity;
  title: string;
  message: string;
  fixHint: string;
  autoFixable: boolean;
  fixAction?: StripeFixAction;
}

export interface StripeDiagnosticReport {
  scannedAt: string;
  projectName: string;
  healthScore: number;
  issues: StripeIssue[];
  summary: string;
}

export interface StripeRepairResult {
  action: StripeFixAction;
  success: boolean;
  message: string;
  files?: string[];
}

export interface PostgresProvisionResult {
  provider: PostgresProvider;
  connectionUrlStored: boolean;
  schemaApplied: boolean;
  reused: boolean;
  projectId?: string;
  projectRef?: string;
  message: string;
}
