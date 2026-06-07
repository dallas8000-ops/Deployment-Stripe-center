import { randomBytes } from "node:crypto";
import { writeFile, readFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import type { DeployConfig, PostgresProvider, PostgresProvisionResult } from "../types.js";
import type { SecretVault } from "../security/vault.js";
import { applyPostgresSchema, getDatabaseUrl, testPostgresConnection } from "./postgres.js";

const NEON_API = "https://console.neon.tech/api/v2";
const SUPABASE_API = "https://api.supabase.com/v1";

export interface PostgresProvisionOptions {
  projectName: string;
  provider?: PostgresProvider;
  region?: string;
  applySchema?: boolean;
  reuseExisting?: boolean;
}

export interface PostgresManifest {
  provider: PostgresProvider;
  projectId?: string;
  projectRef?: string;
  databaseName: string;
  provisionedAt: string;
}

function manifestPath(root: string): string {
  return join(root, ".stripe-installer", "postgres-manifest.json");
}

async function loadManifest(root: string): Promise<PostgresManifest | null> {
  try {
    return JSON.parse(await readFile(manifestPath(root), "utf8")) as PostgresManifest;
  } catch {
    return null;
  }
}

async function saveManifest(root: string, manifest: PostgresManifest): Promise<void> {
  await mkdir(join(root, ".stripe-installer"), { recursive: true });
  await writeFile(manifestPath(root), JSON.stringify(manifest, null, 2), "utf8");
}

function sanitizeName(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/-+/g, "-").slice(0, 48);
}

function generatePassword(): string {
  return randomBytes(24).toString("base64url");
}

async function neonRequest<T>(
  apiKey: string,
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${NEON_API}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Neon API ${res.status}: ${body.slice(0, 200)}`);
  }

  return res.json() as Promise<T>;
}

async function supabaseRequest<T>(
  token: string,
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${SUPABASE_API}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase API ${res.status}: ${body.slice(0, 200)}`);
  }

  return res.json() as Promise<T>;
}

async function provisionNeon(
  vault: SecretVault,
  projectName: string,
  region: string,
  reuseExisting: boolean
): Promise<{ connectionUrl: string; projectId: string; reused: boolean }> {
  const apiKey = await vault.get("NEON_API_KEY");
  if (!apiKey) {
    throw new Error("NEON_API_KEY not in vault — get one at https://console.neon.tech/app/settings/api-keys");
  }

  const safeName = sanitizeName(projectName);

  if (reuseExisting) {
    const listed = await neonRequest<{ projects: { id: string; name: string }[] }>(
      apiKey,
      "/projects"
    );
    const existing = listed.projects.find((p) => p.name === safeName);
    if (existing) {
      const uri = await neonRequest<{ uri: string }>(
        apiKey,
        `/projects/${existing.id}/connection_uri?database_name=neondb&role_name=neondb_owner&pooled=true`
      );
      return { connectionUrl: uri.uri, projectId: existing.id, reused: true };
    }
  }

  const created = await neonRequest<{
    project: { id: string };
    connection_uris?: { connection_uri: string }[];
  }>(apiKey, "/projects", {
    method: "POST",
    body: JSON.stringify({
      project: {
        name: safeName,
        region_id: region,
        pg_version: 16,
      },
    }),
  });

  const pooled =
    created.connection_uris?.[0]?.connection_uri
    ?? (await neonRequest<{ uri: string }>(
      apiKey,
      `/projects/${created.project.id}/connection_uri?database_name=neondb&role_name=neondb_owner&pooled=true`
    )).uri;

  return { connectionUrl: pooled, projectId: created.project.id, reused: false };
}

async function waitForSupabaseProject(
  token: string,
  ref: string,
  maxAttempts = 30
): Promise<void> {
  for (let i = 0; i < maxAttempts; i++) {
    const project = await supabaseRequest<{ status: string }>(token, `/projects/${ref}`);
    if (project.status === "ACTIVE_HEALTHY") return;
    await new Promise((r) => setTimeout(r, 4000));
  }
  throw new Error("Supabase project did not become healthy in time — check dashboard");
}

async function provisionSupabase(
  vault: SecretVault,
  projectName: string,
  region: string,
  reuseExisting: boolean
): Promise<{ connectionUrl: string; projectRef: string; reused: boolean }> {
  const token = await vault.get("SUPABASE_ACCESS_TOKEN");
  if (!token) {
    throw new Error(
      "SUPABASE_ACCESS_TOKEN not in vault — create at https://supabase.com/dashboard/account/tokens"
    );
  }

  const orgId = await vault.get("SUPABASE_ORG_ID");
  if (!orgId) {
    throw new Error(
      "SUPABASE_ORG_ID not in vault — list orgs: curl -H \"Authorization: Bearer $TOKEN\" https://api.supabase.com/v1/organizations"
    );
  }

  const safeName = sanitizeName(projectName);

  if (reuseExisting) {
    const projects = await supabaseRequest<{ id: string; name: string }[]>(token, "/projects");
    const existing = projects.find((p) => p.name === safeName);
    if (existing) {
      const dbPass = await vault.get("SUPABASE_DB_PASSWORD");
      if (!dbPass) {
        throw new Error("Existing Supabase project found but SUPABASE_DB_PASSWORD missing from vault");
      }
      return {
        connectionUrl: `postgresql://postgres:${encodeURIComponent(dbPass)}@db.${existing.id}.supabase.co:5432/postgres?sslmode=require`,
        projectRef: existing.id,
        reused: true,
      };
    }
  }

  const dbPass = generatePassword();
  const created = await supabaseRequest<{ id: string }>(token, "/projects", {
    method: "POST",
    body: JSON.stringify({
      organization_id: orgId,
      name: safeName,
      region,
      db_pass: dbPass,
    }),
  });

  await waitForSupabaseProject(token, created.id);
  await vault.set("SUPABASE_DB_PASSWORD", dbPass);

  return {
    connectionUrl: `postgresql://postgres:${encodeURIComponent(dbPass)}@db.${created.id}.supabase.co:5432/postgres?sslmode=require`,
    projectRef: created.id,
    reused: false,
  };
}

export async function provisionPostgres(
  root: string,
  vault: SecretVault,
  config: DeployConfig,
  opts: PostgresProvisionOptions
): Promise<PostgresProvisionResult> {
  const existingUrl = await getDatabaseUrl(vault);
  if (existingUrl && opts.reuseExisting !== false) {
    const conn = await testPostgresConnection(existingUrl);
    if (conn.ok) {
      return {
        provider: config.postgres?.provider ?? "unknown",
        connectionUrlStored: true,
        schemaApplied: false,
        reused: true,
        message: `Using existing DATABASE_URL (${conn.message})`,
      };
    }
  }

  const provider = opts.provider ?? config.postgres?.provider ?? "neon";
  if (provider !== "neon" && provider !== "supabase") {
    throw new Error(
      `Automated provisioning supports neon and supabase — got "${provider}". Set DATABASE_URL manually for other providers.`
    );
  }

  const region = opts.region ?? config.postgres?.region ?? (provider === "neon" ? "aws-us-east-1" : "us-east-1");
  const reuseExisting = opts.reuseExisting !== false;

  let connectionUrl: string;
  let reused: boolean;
  const manifest: PostgresManifest = {
    provider,
    databaseName: "postgres",
    provisionedAt: new Date().toISOString(),
  };

  if (provider === "neon") {
    const result = await provisionNeon(vault, opts.projectName, region, reuseExisting);
    connectionUrl = result.connectionUrl;
    reused = result.reused;
    manifest.projectId = result.projectId;
  } else {
    const result = await provisionSupabase(vault, opts.projectName, region, reuseExisting);
    connectionUrl = result.connectionUrl;
    reused = result.reused;
    manifest.projectRef = result.projectRef;
  }

  const envVar = config.postgres?.connectionEnvVar ?? "DATABASE_URL";
  await vault.set(envVar, connectionUrl);
  await saveManifest(root, manifest);

  let schemaApplied = false;
  if (opts.applySchema !== false) {
    const schemaResult = await applyPostgresSchema(root, connectionUrl);
    schemaApplied = schemaResult.ok;
    if (!schemaResult.ok) {
      return {
        provider,
        connectionUrlStored: true,
        schemaApplied: false,
        reused,
        projectId: manifest.projectId,
        projectRef: manifest.projectRef,
        message: `Database provisioned but schema failed: ${schemaResult.message}`,
      };
    }
  }

  const conn = await testPostgresConnection(connectionUrl);
  return {
    provider,
    connectionUrlStored: true,
    schemaApplied,
    reused,
    projectId: manifest.projectId,
    projectRef: manifest.projectRef,
    message: reused
      ? `Reused ${provider} project (${conn.message})`
      : `Created ${provider} project (${conn.message})`,
  };
}

export async function getPostgresProvisionStatus(
  root: string,
  vault: SecretVault
): Promise<{ manifest: PostgresManifest | null; connected: boolean; message: string }> {
  const manifest = await loadManifest(root);
  const dbUrl = await getDatabaseUrl(vault);
  if (!dbUrl) {
    return { manifest, connected: false, message: "DATABASE_URL not in vault" };
  }
  const conn = await testPostgresConnection(dbUrl);
  return { manifest, connected: conn.ok, message: conn.message };
}
