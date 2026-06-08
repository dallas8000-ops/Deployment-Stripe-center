const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export interface ApiError {
  error?: string;
  detail?: string;
  [key: string]: unknown;
}

function getTokens() {
  return {
    access: localStorage.getItem("access_token"),
    refresh: localStorage.getItem("refresh_token"),
  };
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem("refresh_token");
  if (!refresh) return null;
  const res = await fetch(`${API_BASE}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { access: string };
  localStorage.setItem("access_token", data.access);
  return data.access;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  const { access } = getTokens();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (access) headers.set("Authorization", `Bearer ${access}`);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new Error(
      "Can't reach the API. Start the backend: npm run dev:backend (from repo root)"
    );
  }

  if (res.status === 401 && retry) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      return apiFetch(path, options, false);
    }
    clearTokens();
    throw new Error("Session expired — please log in again");
  }

  if (!res.ok) {
    let message = res.statusText;
    try {
      const err = (await res.json()) as ApiError;
      message = String(err.error ?? err.detail ?? err.email ?? JSON.stringify(err));
    } catch {
      if (res.status === 404) {
        message = `API not found (${path}) — restart the backend: npm run dev:stop then npm run dev`;
      } else if (res.status === 409 || res.status === 503) {
        message = "Port 8000 is in use by another process. Close old backend terminals, then run npm run dev again.";
      } else if (res.status >= 500) {
        message =
          "Backend error on port 8000 — an old server may still be running. Stop other Daphne processes and run npm run dev again.";
      }
    }
    throw new Error(typeof message === "string" ? message : "Request failed");
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface User {
  id: number;
  email: string;
  display_name: string;
  date_joined: string;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string;
  git_url: string;
  local_path: string;
  framework: string;
  language: string;
  scan_data: Record<string, unknown>;
  last_scanned_at: string | null;
  created_at: string;
  updated_at: string;
  latest_readiness_score?: number | null;
  last_run_status?: string | null;
  production_url?: string;
  active_environment?: "test" | "staging" | "production";
  organization_slug?: string | null;
  organization_name?: string | null;
  org_billing?: {
    saasConfigured: boolean;
    subscriptionActive: boolean;
    needsUpgrade: boolean;
    memberCount: number;
    projectCount: number;
    freeMemberLimit: number;
    freeProjectLimit: number;
  } | null;
}

export interface InvitePreview {
  valid: boolean;
  email?: string;
  role?: string;
  organization?: string;
  organizationSlug?: string;
  expiresAt?: string;
}

export interface PendingInvite {
  id: string;
  email: string;
  role: string;
  invite_url: string;
  created_at: string;
  expires_at: string;
}

export type InviteResult =
  | OrgMember
  | {
      pending: true;
      email: string;
      role: string;
      inviteUrl: string;
      emailSent: boolean;
    };

export const authApi = {
  register: (body: {
    email: string;
    password: string;
    display_name?: string;
    invite_token?: string;
  }) => apiFetch<User>("/auth/register/", { method: "POST", body: JSON.stringify(body) }),

  invitePreview: (token: string) => apiFetch<InvitePreview>(`/invites/${token}/`),

  login: async (email: string, password: string) => {
    const data = await apiFetch<{ access: string; refresh: string }>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(data.access, data.refresh);
    return data;
  },

  me: () => apiFetch<User>("/auth/me/"),

  logout: () => {
    clearTokens();
  },
};

export const projectsApi = {
  list: () => apiFetch<Project[]>("/projects/"),
  create: (body: { name: string; description?: string; git_url?: string; local_path?: string }) =>
    apiFetch<Project>("/projects/", { method: "POST", body: JSON.stringify(body) }),
  get: (slug: string) => apiFetch<Project>(`/projects/${slug}/`),
  update: (
    slug: string,
    body: Partial<{
      name: string;
      description: string;
      git_url: string;
      local_path: string;
      production_url: string;
      active_environment: "test" | "staging" | "production";
      organization_slug: string;
    }>
  ) =>
    apiFetch<Project>(`/projects/${slug}/`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  audit: (slug: string) =>
    apiFetch<{ entries: AuditEntry[] }>(`/projects/${slug}/audit/`),
  scan: (slug: string, local_path?: string) =>
    apiFetch<Project>(`/projects/${slug}/scan/`, {
      method: "POST",
      body: JSON.stringify(local_path ? { local_path } : {}),
    }),
  clone: (slug: string, opts: { branch?: string; force?: boolean; async?: boolean } = {}) =>
    apiFetch<{ action?: string; local_path?: string; status?: string; task_id?: string; project: Project }>(
      `/projects/${slug}/clone/`,
      { method: "POST", body: JSON.stringify(opts) }
    ),
  cloneStatus: (slug: string) =>
    apiFetch<{ status: string; error: string; local_path: string; task_id?: string }>(
      `/projects/${slug}/clone-status/`
    ),
  openPr: (
    slug: string,
    opts: { title?: string; body?: string; commit_message?: string; require_ci_passing?: boolean } = {}
  ) =>
    apiFetch<{ action: string; url: string; number: number; branch: string }>(
      `/projects/${slug}/open-pr/`,
      { method: "POST", body: JSON.stringify(opts) }
    ),
  githubCiStatus: (slug: string, ref?: string) => {
    const qs = ref ? `?ref=${encodeURIComponent(ref)}` : "";
    return apiFetch<GithubCiStatus>(`/projects/${slug}/github/ci-status${qs}`);
  },
  readinessGate: (slug: string) =>
    apiFetch<ReadinessGateResult>(`/projects/${slug}/ci/readiness-gate/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  ciWorkflow: (slug: string) =>
    apiFetch<{ workflow: string; filename: string }>(`/projects/${slug}/ci/workflow/`),
  listApiKeys: (slug: string) =>
    apiFetch<{ keys: ProjectApiKeyRow[] }>(`/projects/${slug}/api-keys/`),
  createApiKey: (slug: string, name: string) =>
    apiFetch<{ id: string; name: string; prefix: string; key: string }>(`/projects/${slug}/api-keys/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  revokeApiKey: (slug: string, keyId: string) =>
    apiFetch<void>(`/projects/${slug}/api-keys/${keyId}/`, { method: "DELETE" }),
  remove: (slug: string) =>
    apiFetch<void>(`/projects/${slug}/`, { method: "DELETE" }),
};

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
  member_count: number;
  my_role: string | null;
  github_installation_id?: number | null;
  github_account?: string;
}

export interface OrgMember {
  id: string;
  email: string;
  display_name: string;
  role: string;
  invited_at: string;
}

export interface GithubCiStatus {
  ref: string;
  state: string;
  success: boolean;
  repository: string;
  checkRuns: { name: string; status: string; conclusion: string | null; htmlUrl: string }[];
}

export interface ReadinessGateResult {
  passed: boolean;
  score: number;
  label: string;
  checks: { id: string; status: string; message: string }[];
  failingCount: number;
}

export interface ProjectApiKeyRow {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export const orgsApi = {
  list: () => apiFetch<Organization[]>("/organizations/"),
  create: (name: string) =>
    apiFetch<Organization>("/organizations/", { method: "POST", body: JSON.stringify({ name }) }),
  members: (orgSlug: string) =>
    apiFetch<{ members: OrgMember[] }>(`/organizations/${orgSlug}/members/`),
  invite: (orgSlug: string, email: string, role = "member") =>
    apiFetch<InviteResult>(`/organizations/${orgSlug}/invite/`, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    }),
  pendingInvites: (orgSlug: string) =>
    apiFetch<{ invites: PendingInvite[] }>(`/organizations/${orgSlug}/pending-invites/`),
  revokeInvite: (orgSlug: string, inviteId: string) =>
    apiFetch<void>(`/organizations/${orgSlug}/pending-invites/${inviteId}/`, { method: "DELETE" }),
  updateMember: (orgSlug: string, memberId: string, role: string) =>
    apiFetch<OrgMember>(`/organizations/${orgSlug}/members/${memberId}/`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  removeMember: (orgSlug: string, memberId: string) =>
    apiFetch<void>(`/organizations/${orgSlug}/members/${memberId}/`, { method: "DELETE" }),
  linkGithub: (orgSlug: string, installationId: number, githubAccount?: string) =>
    apiFetch<Organization>(`/organizations/${orgSlug}/link-github/`, {
      method: "POST",
      body: JSON.stringify({
        installation_id: installationId,
        github_account: githubAccount || "",
      }),
    }),
  githubInstallUrl: (orgSlug: string) =>
    apiFetch<{
      configured: boolean;
      url?: string;
      state?: string;
      callbackUrl?: string;
      message?: string;
      manual?: boolean;
    }>(`/organizations/${orgSlug}/github/install-url/`),
  completeGithubInstall: (
    orgSlug: string,
    body: { installation_id: number; state?: string; setup_action?: string }
  ) =>
    apiFetch<Organization>(`/organizations/${orgSlug}/github/complete-install/`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export interface AgencyBillingInfo {
  saasConfigured: boolean;
  freeMemberLimit: number;
  freeProjectLimit: number;
  organizations: {
    slug: string;
    subscriptionActive: boolean;
    memberCount: number;
    projectCount: number;
  }[];
}

export const agencyApi = {
  dashboard: () =>
    apiFetch<{
      organizations: Organization[];
      projects: Project[];
      stats: { organizationCount: number; projectCount: number };
      billing?: AgencyBillingInfo;
    }>("/agency/dashboard/"),
};

export interface VaultEntry {
  key: string;
  display: string;
  verified: boolean;
  verifiedAt?: string | null;
  verificationMessage?: string | null;
  mode: string;
}

export const vaultApi = {
  init: (projectSlug: string) =>
    apiFetch<{ initialized: boolean; keys: string[]; entries: VaultEntry[] }>(
      `/projects/${projectSlug}/vault/init/`,
      { method: "POST" }
    ),
  keys: (projectSlug: string) =>
    apiFetch<{ keys: string[]; entries: VaultEntry[]; initialized: boolean }>(
      `/projects/${projectSlug}/vault/keys/`
    ),
  set: (projectSlug: string, key: string, value: string) =>
    apiFetch<{ stored: string; keys: string[]; entries: VaultEntry[]; entry: VaultEntry }>(
      `/projects/${projectSlug}/vault/keys/set/`,
      {
        method: "POST",
        body: JSON.stringify({ key, value }),
      }
    ),
  remove: (projectSlug: string, key: string) =>
    apiFetch<{ deleted: string; keys: string[]; entries: VaultEntry[] }>(
      `/projects/${projectSlug}/vault/keys/delete/`,
      {
        method: "POST",
        body: JSON.stringify({ key, confirm: true }),
      }
    ),
  importFromEnv: (projectSlug: string, envFile = ".env.local") =>
    apiFetch<{ imported: string[]; env_file: string; keys: string[]; entries: VaultEntry[] }>(
      `/projects/${projectSlug}/vault/import/`,
      {
        method: "POST",
        body: JSON.stringify({ env_file: envFile }),
      }
    ),
};

export interface KeyCheck {
  valid: boolean;
  mode: string;
  message: string;
}

export interface VerificationResult {
  secretKey: KeyCheck;
  publishableKey: KeyCheck;
  accountId?: string | null;
  accountName?: string | null;
  country?: string | null;
  billingEnabled?: boolean | null;
}

export interface PipelineRunLog {
  step: string;
  status: string;
  message: string;
  detail: boolean;
  score: number | null;
  created_at: string;
}

export interface PipelineRun {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  options: Record<string, unknown>;
  result: Record<string, unknown>;
  error_message: string;
  readiness_score: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  logs?: PipelineRunLog[];
}

export interface DeployRunResult {
  platform?: string;
  productionUrl?: string;
  postgresConnected?: boolean | null;
  nextSteps?: string[];
  manifest?: Record<string, unknown>;
  push?: { success: boolean; message: string } | null;
}

export interface StripeTier {
  name: string;
  description?: string;
  amount: number;
  currency?: string;
  interval: string;
  trialDays?: number;
  features?: string[];
}

export interface StripeConfig {
  appUrl: string;
  provision: {
    reuseExisting: boolean;
    createWebhook: boolean;
    createPortal: boolean;
  };
  tiers: StripeTier[];
}

export const stripeConfigApi = {
  get: (projectSlug: string) =>
    apiFetch<{ config: StripeConfig; exists: boolean; path: string }>(
      `/projects/${projectSlug}/stripe/config/`
    ),
  save: (projectSlug: string, config: StripeConfig) =>
    apiFetch<{ config: StripeConfig; exists: boolean; path: string }>(
      `/projects/${projectSlug}/stripe/config/`,
      { method: "PUT", body: JSON.stringify({ config }) }
    ),
};

export const pipelineApi = {
  verify: (projectSlug: string) =>
    apiFetch<VerificationResult>(`/projects/${projectSlug}/verify/`, { method: "POST" }),

  start: (
    projectSlug: string,
    opts: {
      sync_env?: boolean;
      force?: boolean;
      provision?: boolean;
      generate?: boolean;
      include_readiness?: boolean;
    } = {}
  ) =>
    apiFetch<PipelineRun>(`/projects/${projectSlug}/runs/`, {
      method: "POST",
      body: JSON.stringify(opts),
    }),

  get: (projectSlug: string, runId: string) =>
    apiFetch<PipelineRun>(`/projects/${projectSlug}/runs/${runId}/`),

  list: (projectSlug: string) => apiFetch<PipelineRun[]>(`/projects/${projectSlug}/runs/`),

  downloadRun: async (projectSlug: string, runId: string) => {
    const access = localStorage.getItem("access_token");
    const res = await fetch(`${API_BASE}/projects/${projectSlug}/runs/${runId}/download/`, {
      headers: access ? { Authorization: `Bearer ${access}` } : {},
    });
    if (!res.ok) {
      const err = (await res.json().catch(() => ({}))) as ApiError;
      throw new Error(err.error || err.detail || "Download failed");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${projectSlug}-stripe-${runId}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  },

  downloadCodegen: async (projectSlug: string) => {
    const access = localStorage.getItem("access_token");
    const res = await fetch(`${API_BASE}/projects/${projectSlug}/codegen/download/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = (await res.json().catch(() => ({}))) as ApiError;
      throw new Error(err.error || err.detail || "Download failed");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${projectSlug}-stripe-codegen.zip`;
    a.click();
    URL.revokeObjectURL(url);
  },
};

export interface ReadinessCheck {
  id: string;
  category: string;
  name: string;
  status: "pass" | "warn" | "fail";
  message: string;
  fix?: string | null;
}

export interface ReadinessResult {
  score: number;
  label: string;
  checks: ReadinessCheck[];
}

export interface StripeIssue {
  id: string;
  category: string;
  severity: "error" | "warning" | "info";
  title: string;
  message: string;
  fix_hint: string;
  auto_fixable: boolean;
  fix_action?: string | null;
}

export interface DiagnosticReport {
  scannedAt: string;
  projectName: string;
  healthScore: number;
  issues: StripeIssue[];
  summary: string;
}

export interface FixResult {
  repairs: { action: string; success: boolean; message: string; files?: string[] }[];
  report: DiagnosticReport;
}

export const healthApi = {
  diagnose: (projectSlug: string) =>
    apiFetch<DiagnosticReport>(`/projects/${projectSlug}/diagnose/`, { method: "POST" }),

  readiness: (projectSlug: string) =>
    apiFetch<ReadinessResult>(`/projects/${projectSlug}/readiness/`),

  fix: (
    projectSlug: string,
    opts: { all?: boolean; issue_ids?: string[]; action?: string; force?: boolean } = {}
  ) =>
    apiFetch<FixResult>(`/projects/${projectSlug}/fix/`, {
      method: "POST",
      body: JSON.stringify(opts),
    }),
};

export interface BillingPlan {
  tier: string;
  priceId: string;
  label: string;
  amount: number;
  currency: string;
}

export interface SubscriptionInfo {
  tier: string | null;
  status: string;
  isActive: boolean;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
  customerId: string | null;
}

export interface OrgSubscriptionInfo extends SubscriptionInfo {
  organization: string;
}

export const billingApi = {
  plans: () => apiFetch<{ configured: boolean; plans: BillingPlan[] }>("/billing/plans/"),

  subscription: () => apiFetch<SubscriptionInfo>("/billing/subscription/"),

  orgSubscription: (orgSlug: string) =>
    apiFetch<OrgSubscriptionInfo>(`/billing/org/subscription/?org=${encodeURIComponent(orgSlug)}`),

  checkout: (priceId: string) =>
    apiFetch<{ url: string }>("/billing/checkout/", {
      method: "POST",
      body: JSON.stringify({ priceId }),
    }),

  orgCheckout: (orgSlug: string, priceId: string) =>
    apiFetch<{ url: string }>("/billing/org/checkout/", {
      method: "POST",
      body: JSON.stringify({ org: orgSlug, priceId }),
    }),

  portal: () =>
    apiFetch<{ url: string }>("/billing/portal/", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  orgPortal: (orgSlug: string) =>
    apiFetch<{ url: string }>("/billing/org/portal/", {
      method: "POST",
      body: JSON.stringify({ org: orgSlug }),
    }),
};

export interface PostgresStatus {
  configured: boolean;
  message: string;
  schemaApplied?: boolean;
  connected?: boolean;
  connectionMessage?: string;
  manifest?: Record<string, unknown> | null;
}

export interface PostgresProvisionResult {
  provider: string;
  stored: boolean;
  reused: boolean;
  message: string;
  schema?: { ok: boolean; message: string };
}

export interface DeployReadinessResult extends ReadinessResult {
  postgres: PostgresStatus;
}

export interface DeployEnvironment {
  url: string;
}

export interface DeployConfig {
  productionUrl: string;
  environments?: {
    test?: DeployEnvironment;
    staging?: DeployEnvironment;
    production?: DeployEnvironment;
  };
  platform: "vercel" | "railway" | "render" | "fly" | "docker" | "unknown";
  postgres: {
    provider: "neon" | "supabase" | "railway" | "render" | "self-hosted" | "unknown";
    connectionEnvVar: string;
    autoProvision: boolean;
  };
  monitoring: { healthCheck: boolean };
  backup: { enabled: boolean; retentionDays: number };
}

export const deployApi = {
  postgresStatus: (projectSlug: string) =>
    apiFetch<PostgresStatus>(`/projects/${projectSlug}/postgres/status/`),

  postgresSchema: (projectSlug: string) =>
    apiFetch<{ schema: string }>(`/projects/${projectSlug}/postgres/schema/`),

  provisionPostgres: (
    projectSlug: string,
    opts: {
      provider?: "neon" | "supabase" | "railway" | "render" | "self-hosted";
      region?: string;
      reuse?: boolean;
      apply_schema?: boolean;
    } = {}
  ) =>
    apiFetch<PostgresProvisionResult>(`/projects/${projectSlug}/postgres/provision/`, {
      method: "POST",
      body: JSON.stringify(opts),
    }),

  testPostgres: (projectSlug: string) =>
    apiFetch<{ ok: boolean; message: string }>(`/projects/${projectSlug}/postgres/test/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  applySchema: (projectSlug: string) =>
    apiFetch<{ ok: boolean; message: string }>(`/projects/${projectSlug}/postgres/apply-schema/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  deployReadiness: (projectSlug: string, appUrl?: string) => {
    const q = appUrl ? `?app_url=${encodeURIComponent(appUrl)}` : "";
    return apiFetch<DeployReadinessResult>(`/projects/${projectSlug}/deploy/readiness/${q}`);
  },

  deployRun: (
    projectSlug: string,
    opts: {
      provision?: boolean;
      generate?: boolean;
      sync_env?: boolean;
      force?: boolean;
      include_infra?: boolean;
      provision_postgres?: boolean;
      push?: boolean;
      postgres_provider?: "neon" | "supabase";
      app_url?: string;
    } = {}
  ) =>
    apiFetch<PipelineRun>(`/projects/${projectSlug}/deploy/run/`, {
      method: "POST",
      body: JSON.stringify(opts),
    }),

  deployPush: (projectSlug: string, platform?: string) =>
    apiFetch<{ success: boolean; platform: string; message: string }>(
      `/projects/${projectSlug}/deploy/push/`,
      {
        method: "POST",
        body: JSON.stringify(platform ? { platform } : {}),
      }
    ),

  getDeployConfig: (projectSlug: string) =>
    apiFetch<{ config: DeployConfig; exists: boolean; path: string }>(
      `/projects/${projectSlug}/deploy/config/`
    ),

  saveDeployConfig: (projectSlug: string, config: DeployConfig) =>
    apiFetch<{ config: DeployConfig; exists: boolean; path: string }>(
      `/projects/${projectSlug}/deploy/config/`,
      { method: "PUT", body: JSON.stringify({ config }) }
    ),

  infraPreview: (projectSlug: string, appUrl?: string) => {
    const q = appUrl ? `?app_url=${encodeURIComponent(appUrl)}` : "";
    return apiFetch<{ fileCount: number; paths: string[] }>(
      `/projects/${projectSlug}/deploy/infra/preview/${q}`
    );
  },

  generateInfra: (
    projectSlug: string,
    opts: { force?: boolean; app_url?: string } = {}
  ) =>
    apiFetch<{
      fileCount: number;
      paths: string[];
      written: { path: string; action: string }[];
      skipped: string[];
    }>(`/projects/${projectSlug}/deploy/infra/generate/`, {
      method: "POST",
      body: JSON.stringify(opts),
    }),
};

export const aiApi = {
  recommend: (projectSlug: string) =>
    apiFetch<{ recommendations: string; provider: string }>(
      `/projects/${projectSlug}/ai/recommend/`,
      { method: "POST", body: JSON.stringify({}) }
    ),

  fixCopilot: (projectSlug: string) =>
    apiFetch<{ items: FixCopilotItem[]; provider: string }>(
      `/projects/${projectSlug}/ai/fix-copilot/`,
      { method: "POST", body: JSON.stringify({}) }
    ),

  readinessCoach: (projectSlug: string) =>
    apiFetch<{ items: ReadinessCoachItem[]; provider: string; score: number | null; label: string | null }>(
      `/projects/${projectSlug}/ai/readiness-coach/`,
      { method: "POST", body: JSON.stringify({}) }
    ),

  nlConfig: (projectSlug: string, instruction: string, apply = false) =>
    apiFetch<{ stripeConfig: StripeConfig; deployConfig: DeployConfig; provider: string; written: string[] }>(
      `/projects/${projectSlug}/ai/nl-config/`,
      { method: "POST", body: JSON.stringify({ instruction, apply }) }
    ),

  catalogStrategist: (projectSlug: string, businessDescription: string, apply = false) =>
    apiFetch<{ stripeConfig: StripeConfig; summary: string; provider: string; written: string[] }>(
      `/projects/${projectSlug}/ai/catalog-strategist/`,
      { method: "POST", body: JSON.stringify({ business_description: businessDescription, apply }) }
    ),

  handoffPack: (projectSlug: string, productionUrl?: string) =>
    apiFetch<HandoffPack & { provider: string }>(`/projects/${projectSlug}/ai/handoff-pack/`, {
      method: "POST",
      body: JSON.stringify(productionUrl ? { production_url: productionUrl } : {}),
    }),

  webhookIncident: (
    projectSlug: string,
    opts: { payload?: string; eventId?: string }
  ) =>
    apiFetch<{ analysis: string; provider: string; eventId?: string; fetchedFromStripe?: boolean }>(
      `/projects/${projectSlug}/ai/webhook-incident/`,
      {
        method: "POST",
        body: JSON.stringify({
          payload: opts.payload,
          event_id: opts.eventId,
        }),
      }
    ),
};

export interface FixCopilotItem {
  issueId: string;
  explanation: string;
  fixAction?: string | null;
  autoFixable?: boolean;
  severity?: string;
}

export interface ReadinessCoachItem {
  checkId: string;
  coachSteps: string;
  estimatedMinutes?: number;
}

export interface HandoffPack {
  prDescription: string;
  opsRunbook: string;
  testChecklist: string;
}

export interface DriftResult {
  driftCount: number;
  items: DriftItem[];
  manifestPriceCount: number;
  checkedAt?: string;
}

export interface AuditEntry {
  id: number;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
  actor: string | null;
}

export const monitoringApi = {
  drift: (projectSlug: string) =>
    apiFetch<DriftResult>(`/projects/${projectSlug}/drift/`),
  driftResync: (projectSlug: string) =>
    apiFetch<{ before: DriftResult; after: DriftResult; repair: { action: string; success: boolean; message: string } }>(
      `/projects/${projectSlug}/drift/resync/`,
      { method: "POST", body: JSON.stringify({}) }
    ),
  webhookHealth: (projectSlug: string) =>
    apiFetch<WebhookHealthResult>(`/projects/${projectSlug}/webhook-health/`),
};

export interface DriftItem {
  category: string;
  severity: string;
  message: string;
  fix: string;
}

export interface WebhookHealthResult {
  expectedWebhookUrl: string | null;
  endpoints: { id: string; url: string; status: string; matchesExpected: boolean | null }[];
  recentEventTypes: Record<string, number>;
  issues: { severity: string; message: string; fix: string }[];
  healthy: boolean;
};
