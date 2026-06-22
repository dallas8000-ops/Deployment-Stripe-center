const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

/** Resolved API origin for UI hints (local dev vs production). */
export function apiConnectionLabel(): string {
  const base = import.meta.env.VITE_API_BASE ?? "/api/v1";
  if (base.startsWith("http")) {
    try {
      return new URL(base).host;
    } catch {
      return base;
    }
  }
  if (typeof window !== "undefined") {
    return window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost"
      ? "local dev (unified app)"
      : `${window.location.hostname} (unified app)`;
  }
  return "unified app";
}

export interface ApiError {
  error?: string;
  detail?: string | Array<{ message?: string } | string> | Record<string, unknown>;
  email?: string;
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

export async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem("refresh_token");
  if (!refresh) return null;
  const res = await fetch(`${API_BASE}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { access: string; refresh?: string };
  localStorage.setItem("access_token", data.access);
  if (data.refresh) {
    localStorage.setItem("refresh_token", data.refresh);
  }
  return data.access;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  const isAuthAttempt =
    path.startsWith("/auth/login") || path.startsWith("/auth/register");
  const { access } = getTokens();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (access && !isAuthAttempt) {
    headers.set("Authorization", `Bearer ${access}`);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new Error(
      "Can't reach the API. Start the backend: npm run dev:backend (from repo root)"
    );
  }

  if (res.status === 401 && retry && !isAuthAttempt) {
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
      const detail = err.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = detail
          .map((d) => (typeof d === "string" ? d : (d as { message?: string }).message))
          .filter(Boolean)
          .join(" ");
      } else if (detail && typeof detail === "object") {
        message = JSON.stringify(detail);
      } else {
        message = String(err.error ?? err.email ?? JSON.stringify(err));
      }
    } catch {
      if (res.status === 404) {
        message = `API not found (${path}) — stale backend. Run: npm run dev:stop  and then  npm run dev`;
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
  mfa_enabled?: boolean;
}

export interface LoginResponse {
  access?: string;
  refresh?: string;
  mfa_required?: boolean;
  mfa_token?: string;
}

export interface SsoConfig {
  enabled: boolean;
  login_url?: string;
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
  stripe_exempt?: boolean;
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

  login: async (email: string, password: string): Promise<LoginResponse> => {
    clearTokens();
    const data = await apiFetch<LoginResponse>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (data.access && data.refresh) {
      setTokens(data.access, data.refresh);
    }
    return data;
  },

  verifyMfa: async (mfa_token: string, code: string, recovery_code?: string) => {
    const data = await apiFetch<{ access: string; refresh: string }>("/auth/mfa/verify/", {
      method: "POST",
      body: JSON.stringify({ mfa_token, code, recovery_code }),
    });
    setTokens(data.access, data.refresh);
    return data;
  },

  mfaStatus: () => apiFetch<{ mfa_enabled: boolean }>("/auth/mfa/status/"),

  mfaEnrollStart: () =>
    apiFetch<{ secret: string; provisioning_uri: string; issuer: string }>(
      "/auth/mfa/enroll/start/",
      { method: "POST", body: "{}" }
    ),

  mfaEnrollConfirm: (code: string) =>
    apiFetch<{ mfa_enabled: boolean; recovery_codes: string[] }>("/auth/mfa/enroll/confirm/", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  mfaDisable: (password: string, code: string) =>
    apiFetch<{ mfa_enabled: boolean }>("/auth/mfa/disable/", {
      method: "POST",
      body: JSON.stringify({ password, code }),
    }),

  ssoConfig: () => apiFetch<SsoConfig>("/auth/sso/config/"),

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
  readable?: boolean;
}

export interface VaultHealth {
  masterKeyValid: boolean;
  unreadableCount: number;
  totalCount: number;
}

export interface SecretSourceInfo {
  kind: "local_store" | "legacy_vault" | "env_file" | "portfolio_path";
  label: string;
  path: string;
  status: "ready" | "missing" | "needs_passphrase" | "empty";
  keyCount: number;
  keys: string[];
  note?: string;
}

export interface VaultSourcesResponse {
  projectSlug: string;
  projectRoot: string | null;
  dataDir: string;
  localVaultPath: string;
  sources: SecretSourceInfo[];
}

export const vaultApi = {
  init: (projectSlug: string) =>
    apiFetch<{ initialized: boolean; keys: string[]; entries: VaultEntry[] }>(
      `/projects/${projectSlug}/vault/init/`,
      { method: "POST" }
    ),
  keys: (projectSlug: string) =>
    apiFetch<{ keys: string[]; entries: VaultEntry[]; initialized: boolean; vaultHealth?: VaultHealth }>(
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
  copy: (projectSlug: string, key: string) =>
    apiFetch<{ key: string; value: string; copyable: boolean }>(
      `/projects/${projectSlug}/vault/keys/copy/`,
      {
        method: "POST",
        body: JSON.stringify({ key }),
      }
    ),
  pullFromHub: (projectSlug: string) =>
    apiFetch<{
      copied: string[];
      message: string;
      keys: string[];
      entries: VaultEntry[];
      vaultHealth?: VaultHealth;
    }>(`/projects/${projectSlug}/vault/pull-from-hub/`, { method: "POST" }),
  importFromEnv: (projectSlug: string, envFile: string | "auto" = "auto") =>
    apiFetch<{
      imported: string[];
      env_file: string;
      keys: string[];
      entries: VaultEntry[];
      vaultHealth?: VaultHealth;
    }>(
      `/projects/${projectSlug}/vault/import/`,
      {
        method: "POST",
        body: JSON.stringify({ env_file: envFile }),
      }
    ),
  sources: (projectSlug: string) =>
    apiFetch<VaultSourcesResponse>(`/projects/${projectSlug}/vault/sources/`),
  importAll: (
    projectSlug: string,
    opts?: { legacyPassphrase?: string; includeLegacy?: boolean; includeEnv?: boolean }
  ) =>
    apiFetch<{
      imported: string[];
      importedBySource: Record<string, string[]>;
      localVaultPath: string;
      projectRoot: string | null;
      errors: string[];
      keys: string[];
      entries: VaultEntry[];
      vaultHealth?: VaultHealth;
    }>(`/projects/${projectSlug}/vault/import-all/`, {
      method: "POST",
      body: JSON.stringify({
        legacy_passphrase: opts?.legacyPassphrase ?? "",
        include_legacy: opts?.includeLegacy ?? true,
        include_env: opts?.includeEnv ?? true,
      }),
    }),
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
  /** API host (webhooks) */
  productionUrl?: string | null;
  /** Railway web frontend — live view */
  webProductionUrl?: string | null;
  /** Railway /demo — primary live experience */
  demoUrl?: string | null;
  /** Optional custom domain for portfolio Live demo button only */
  portfolioDemoUrl?: string | null;
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
      throw new Error(
        err.error ||
          (typeof err.detail === "string" ? err.detail : undefined) ||
          "Download failed"
      );
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
      throw new Error(
        err.error ||
          (typeof err.detail === "string" ? err.detail : undefined) ||
          "Download failed"
      );
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

export interface PlaybookStep {
  order: number;
  title: string;
  detail: string;
  where: "stripe_dashboard" | "hosting" | "vault" | "installer";
  url?: string | null;
  confirm?: string;
}

export interface AdvisorFinding {
  rootCause: string;
  severity: "error" | "warning" | "info";
  title: string;
  summary: string;
  playbook: PlaybookStep[];
  metrics?: Record<string, unknown>;
}

export interface StripeAdvisorReport {
  scannedAt: string;
  projectName: string;
  projectSlug: string;
  primaryRootCause: string;
  webhookErrorRisk: boolean;
  summary: string;
  dashboardLinks: { keys: string; webhooks: string };
  findings: AdvisorFinding[];
  checks: Record<string, unknown>;
}

export interface SetupHubStep {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
}

export interface SetupHubStatus {
  projectSlug: string;
  projectName: string;
  vaultHealth: {
    unreadableCount: number;
    totalCount: number;
  };
  verification: VerificationResult;
  registryPath: string;
  registryApp: Record<string, unknown> | null;
  expectedWebhookUrl: string;
  productionUrl: string;
  webProductionUrl?: string;
  demoUrl?: string;
  portfolioDemoUrl?: string;
  lastPortfolioAuditSummary: Record<string, unknown> | null;
  lastPortfolioAuditRegistryGaps: Array<Record<string, string>>;
  steps: SetupHubStep[];
  readyForPipeline: boolean;
  platformAutomation?: {
    masterKey: { stable: boolean; detail: string };
    vault: { unreadableCount: number; totalCount: number };
    deployPlatform: string;
    railway: { hasToken: boolean; projectId?: string | null; serviceId?: string | null };
    steps?: SetupHubStep[];
    readyForAutomation?: boolean;
  };
  portfolioSummary?: {
    totalApps: number;
    stripeBillingCount: number;
    stripeExemptCount: number;
    stripeExemptApps: Array<{ id: string; name: string; projectSlug?: string }>;
    stripeBillingApps: Array<{ id: string; name: string; projectSlug?: string }>;
  };
  stripeExempt?: boolean;
  isHubProject?: boolean;
  hubSlug?: string;
}

export interface SetupHubActionResult {
  ok?: boolean;
  error?: string;
  status?: SetupHubStatus;
  audit?: Record<string, unknown>;
  results?: Array<Record<string, unknown>>;
  expectedWebhookUrl?: string;
  vaultSecretsCleared?: number;
  message?: string;
  actions?: Array<Record<string, unknown>>;
  projects?: Array<{ slug: string; ok: boolean; platform: string; steps: Array<Record<string, unknown>> }>;
  steps?: Array<{ step: string; ok: boolean; detail: string }>;
}

export const setupHubApi = {
  status: (projectSlug: string) =>
    apiFetch<SetupHubStatus>(`/projects/${projectSlug}/setup-hub/`),

  reset: (projectSlug: string, clearVault = false) =>
    apiFetch<SetupHubActionResult>(`/projects/${projectSlug}/setup-hub/actions/`, {
      method: "POST",
      body: JSON.stringify({ action: "reset", clearVault }),
    }),

  audit: (projectSlug: string) =>
    apiFetch<SetupHubActionResult>(`/projects/${projectSlug}/setup-hub/actions/`, {
      method: "POST",
      body: JSON.stringify({ action: "audit" }),
    }),

  registerWebhooks: (projectSlug: string, dryRun = false) =>
    apiFetch<SetupHubActionResult>(`/projects/${projectSlug}/setup-hub/actions/`, {
      method: "POST",
      body: JSON.stringify({ action: "register_webhooks", dryRun }),
    }),

  syncRegistry: (projectSlug: string) =>
    apiFetch<SetupHubActionResult>(`/projects/${projectSlug}/setup-hub/actions/`, {
      method: "POST",
      body: JSON.stringify({ action: "sync_registry" }),
    }),

  syncVaultToProjects: (projectSlug: string) =>
    apiFetch<SetupHubActionResult>(`/projects/${projectSlug}/setup-hub/actions/`, {
      method: "POST",
      body: JSON.stringify({ action: "sync_vault" }),
    }),

  bootstrapPlatform: (projectSlug: string) =>
    apiFetch<SetupHubActionResult>(`/projects/${projectSlug}/setup-hub/actions/`, {
      method: "POST",
      body: JSON.stringify({ action: "bootstrap_platform" }),
    }),

  automateDeploy: (projectSlug: string) =>
    apiFetch<SetupHubActionResult>(`/projects/${projectSlug}/setup-hub/actions/`, {
      method: "POST",
      body: JSON.stringify({ action: "automate_deploy" }),
    }),

  reconcileMasterKey: (projectSlug: string) =>
    apiFetch<SetupHubActionResult>(`/projects/${projectSlug}/setup-hub/actions/`, {
      method: "POST",
      body: JSON.stringify({ action: "reconcile_master_key" }),
    }),
};

export const healthApi = {
  diagnose: (projectSlug: string) =>
    apiFetch<DiagnosticReport>(`/projects/${projectSlug}/diagnose/`, { method: "POST" }),

  stripeAdvisor: (projectSlug: string) =>
    apiFetch<StripeAdvisorReport>(`/projects/${projectSlug}/stripe-advisor/`, { method: "POST" }),

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

  checkout: (priceId: string, domain: string) =>
    apiFetch<{ url: string }>("/billing/checkout/", {
      method: "POST",
      body: JSON.stringify({ priceId, domain }),
    }),

  orgCheckout: (orgSlug: string, priceId: string, domain: string) =>
    apiFetch<{ url: string }>("/billing/org/checkout/", {
      method: "POST",
      body: JSON.stringify({ org: orgSlug, priceId, domain }),
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

export interface MyLicense {
  key: string;
  domain: string;
  status: string;
  maxInstances: number;
  activeInstances: number;
  expiryDate: string | null;
  createdAt: string;
}

export const licenseApi = {
  myLicenses: () => apiFetch<{ licenses: MyLicense[] }>("/license/me/"),
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
  platform: "vercel" | "railway" | "fly" | "docker" | "unknown";
  postgres: {
    provider: "neon" | "supabase" | "railway" | "self-hosted" | "unknown";
    connectionEnvVar: string;
    autoProvision: boolean;
  };
  monitoring: { healthCheck: boolean };
  backup: { enabled: boolean; retentionDays: number };
}

export interface DeployPreflightResult {
  ok: boolean;
  issues: string[];
  warnings: string[];
  platform: string;
  railway: Record<string, unknown>;
}

export const deployApi = {
  postgresStatus: (projectSlug: string) =>
    apiFetch<PostgresStatus>(`/projects/${projectSlug}/postgres/status/`),

  postgresSchema: (projectSlug: string) =>
    apiFetch<{ schema: string }>(`/projects/${projectSlug}/postgres/schema/`),

  provisionPostgres: (
    projectSlug: string,
    opts: {
      provider?: "neon" | "supabase" | "railway" | "self-hosted";
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

  deployPreflight: (projectSlug: string, opts: { push_railway_env?: boolean } = {}) => {
    const params = new URLSearchParams();
    if (opts.push_railway_env === false) params.set("push_railway_env", "false");
    const q = params.toString() ? `?${params}` : "";
    return apiFetch<DeployPreflightResult>(`/projects/${projectSlug}/deploy/preflight/${q}`);
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
      push_railway_env?: boolean;
      postgres_provider?: "neon" | "supabase" | "railway" | "self-hosted";
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

  pushEnvToPlatform: (
    projectSlug: string,
    opts: {
      platform: "railway";
      service_id?: string;
      project_id?: string;
      environment_id?: string;
      keys?: string[];
      /** Inline vars merged last (override preset + vault). */
      variables?: Record<string, string>;
      /** Named template, e.g. kistie-store or silverfox */
      preset?: string;
      /** Resolve Railway project/service IDs from vault + API when omitted */
      auto_resolve?: boolean;
    }
  ) =>
    apiFetch<{
      pushed: string[];
      message: string;
      environmentId?: string;
      preset?: string;
      projectId?: string;
      serviceId?: string;
    }>(
      `/projects/${projectSlug}/deploy/env-push/`,
      { method: "POST", body: JSON.stringify(opts) }
    ),
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

export interface TransferProviderStatus {
  provider: string;
  liveEnabled: boolean;
  status: string;
  capabilities: string[];
  message: string;
}

export const transferApi = {
  moduleStatus: () =>
    apiFetch<{
      module: string;
      status: string;
      message: string;
      capabilities: Record<string, string>;
    }>("/transfer/status/"),

  providerStatus: () =>
    apiFetch<{
      providers: TransferProviderStatus[];
      serverConfig: Record<string, unknown>;
    }>("/transfer/providers/status/"),

  githubImport: (repoUrl: string, branch?: string, projectSlug?: string) =>
    apiFetch<Record<string, unknown>>("/transfer/github/import/", {
      method: "POST",
      body: JSON.stringify({ repoUrl, branch, projectSlug }),
    }),

  projectGithubImport: (projectSlug: string, repoUrl?: string, branch?: string) =>
    apiFetch<Record<string, unknown>>(`/projects/${projectSlug}/transfer/github/import/`, {
      method: "POST",
      body: JSON.stringify({ repoUrl: repoUrl || "", branch }),
    }),

  projectDeploy: (projectSlug: string, body: Record<string, unknown>) =>
    apiFetch<{ result: Record<string, unknown> }>(`/projects/${projectSlug}/transfer/deploy/`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  projectDeployHistory: (projectSlug: string) =>
    apiFetch<{ runs: Array<Record<string, unknown>> }>(
      `/projects/${projectSlug}/transfer/deploy/history/`
    ),

  refreshDeployStatus: (projectSlug: string, deploymentId: string) =>
    apiFetch<{ run: Record<string, unknown> }>(
      `/projects/${projectSlug}/transfer/deploy/status/${deploymentId}/`,
      { method: "POST", body: JSON.stringify({}) }
    ),

  railwayEnvBackup: (serviceId: string, serviceName?: string, saveToDisk = true) =>
    apiFetch<Record<string, unknown>>("/transfer/env/backup/railway/", {
      method: "POST",
      body: JSON.stringify({ serviceId, serviceName, saveToDisk }),
    }),

  transferStart: (body: Record<string, unknown>, projectSlug?: string) =>
    apiFetch<{ run: Record<string, unknown> }>(
      projectSlug ? `/projects/${projectSlug}/transfer/start/` : "/transfer/start/",
      { method: "POST", body: JSON.stringify(body) }
    ),

  transferStop: () =>
    apiFetch<{ stopped: boolean; run: Record<string, unknown> }>("/transfer/stop/", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  transferRunStatus: () =>
    apiFetch<{ run: Record<string, unknown> }>("/transfer/runs/status/"),

  transferRunHistory: (projectSlug?: string, limit = 10) =>
    apiFetch<{ runs: Array<Record<string, unknown>>; nextCursor?: string | null }>(
      projectSlug
        ? `/projects/${projectSlug}/transfer/runs/history/?limit=${limit}`
        : `/transfer/runs/history/?limit=${limit}`
    ),

  transferReplay: (runId: string) =>
    apiFetch<{ run: Record<string, unknown> }>(`/transfer/runs/replay/${runId}/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  transferMetrics: () =>
    apiFetch<{
      summary: Record<string, number>;
      organization: Record<string, unknown>;
      alerts: Array<Record<string, unknown>>;
      schedulingPolicy: Record<string, unknown>;
      generatedAt: string;
    }>("/transfer/runs/metrics/"),

  transferAudit: () =>
    apiFetch<{
      entries: Array<Record<string, unknown>>;
      valid: { valid: boolean; brokenAt: number | null };
    }>("/transfer/audit/"),

  transferAuditExport: () =>
    apiFetch<Record<string, unknown>>("/transfer/audit/export/"),

  platformSetupAudit: () =>
    apiFetch<{ summary: Record<string, unknown>; tasks: Array<Record<string, unknown>> }>(
      "/transfer/platform/setup-audit/"
    ),

  platformSetupRun: (actionId: string) =>
    apiFetch<Record<string, unknown>>("/transfer/platform/setup-run/", {
      method: "POST",
      body: JSON.stringify({ actionId }),
    }),
};

export interface TransferDeployResult {
  deploymentId?: string;
  appName?: string;
  succeeded?: boolean;
  liveUrl?: string;
  framework?: { framework: string; confidence: number };
  stages?: Array<{ stage: string; status: string; detail: string }>;
  liveExecution?: {
    fullyLive: boolean;
    message: string;
    liveStages: string[];
    simulatedStages: string[];
  };
}

export interface TransferImportResult {
  repository?: { fullName: string; branch: string; url: string };
  files?: string[];
  packageJson?: Record<string, unknown> | null;
  framework?: { framework: string; confidence: number; buildCommand?: string; startCommand?: string };
  project?: { appName: string; repoUrl: string; branch: string };
}

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
