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
      "Can't reach the API. Start the backend: cd saas/backend && .venv\\Scripts\\daphne.exe -b 127.0.0.1 -p 8000 config.asgi:application"
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
      if (res.status >= 500) {
        message =
          "Server error — is the backend running on port 8000? (npm run dev:backend from saas/)";
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
}

export const authApi = {
  register: (body: { email: string; password: string; display_name?: string }) =>
    apiFetch<User>("/auth/register/", { method: "POST", body: JSON.stringify(body) }),

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
  scan: (slug: string, local_path?: string) =>
    apiFetch<Project>(`/projects/${slug}/scan/`, {
      method: "POST",
      body: JSON.stringify(local_path ? { local_path } : {}),
    }),
  remove: (slug: string) =>
    apiFetch<void>(`/projects/${slug}/`, { method: "DELETE" }),
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
}

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

export const billingApi = {
  plans: () => apiFetch<{ configured: boolean; plans: BillingPlan[] }>("/billing/plans/"),

  subscription: () => apiFetch<SubscriptionInfo>("/billing/subscription/"),

  checkout: (priceId: string) =>
    apiFetch<{ url: string }>("/billing/checkout/", {
      method: "POST",
      body: JSON.stringify({ priceId }),
    }),

  portal: () =>
    apiFetch<{ url: string }>("/billing/portal/", {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
