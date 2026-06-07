import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { PostgresProvider } from "../types.js";
import type { SecretVault } from "../security/vault.js";

const DATABASE_URL_PATTERN = /^postgres(ql)?:\/\/.+/i;

export function postgresSchema(): string {
  return `-- Stripe Installer — PostgreSQL schema
-- Tracks customers and subscriptions synced from Stripe webhooks

CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT UNIQUE NOT NULL,
  name          TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stripe_customers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
  stripe_customer_id TEXT UNIQUE NOT NULL,
  email           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID REFERENCES users(id) ON DELETE SET NULL,
  stripe_subscription_id TEXT UNIQUE NOT NULL,
  stripe_customer_id    TEXT NOT NULL,
  stripe_price_id       TEXT,
  status                TEXT NOT NULL,
  tier                  TEXT,
  current_period_end    TIMESTAMPTZ,
  cancel_at_period_end  BOOLEAN DEFAULT FALSE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stripe_event_id TEXT UNIQUE NOT NULL,
  type        TEXT NOT NULL,
  processed   BOOLEAN DEFAULT FALSE,
  payload     JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_customer ON subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_webhook_events_type ON webhook_events(type);
`;
}

export function postgresClientLib(dbImportPath = "./db"): string {
  return `import pg from "pg";

const { Pool } = pg;

let pool: pg.Pool | null = null;

export function getPool(): pg.Pool {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) throw new Error("DATABASE_URL is not set");
    pool = new Pool({
      connectionString,
      ssl: process.env.NODE_ENV === "production" ? { rejectUnauthorized: false } : undefined,
      max: 10,
    });
  }
  return pool;
}

export async function query<T extends pg.QueryResultRow = pg.QueryResultRow>(
  text: string,
  params?: unknown[]
): Promise<pg.QueryResult<T>> {
  return getPool().query<T>(text, params);
}
`;
}

export function postgresWebhookSync(dbImport = "@/lib/db"): string {
  return `import type Stripe from "stripe";
import { query } from "${dbImport}";

export async function linkCustomerFromCheckout(session: Stripe.Checkout.Session) {
  const customerId =
    typeof session.customer === "string" ? session.customer : session.customer?.id;
  const email = session.customer_email ?? session.customer_details?.email ?? null;
  const userId = session.client_reference_id ?? session.metadata?.userId ?? null;
  if (!customerId) return;

  const isUuid = userId && /^[0-9a-f-]{36}$/i.test(userId);
  if (isUuid) {
    await query(
      \`INSERT INTO stripe_customers (stripe_customer_id, email, user_id)
       VALUES ($1, $2, $3::uuid)
       ON CONFLICT (stripe_customer_id) DO UPDATE SET
         email = COALESCE(EXCLUDED.email, stripe_customers.email),
         user_id = COALESCE(EXCLUDED.user_id, stripe_customers.user_id)\`,
      [customerId, email, userId]
    );
  } else {
    await query(
      \`INSERT INTO stripe_customers (stripe_customer_id, email)
       VALUES ($1, $2)
       ON CONFLICT (stripe_customer_id) DO UPDATE SET
         email = COALESCE(EXCLUDED.email, stripe_customers.email)\`,
      [customerId, email]
    );
  }
}

export async function linkCustomerToUser(userId: string, stripeCustomerId: string, email?: string | null) {
  await query(
    \`INSERT INTO stripe_customers (user_id, stripe_customer_id, email)
     VALUES ($1::uuid, $2, $3)
     ON CONFLICT (stripe_customer_id) DO UPDATE SET
       user_id = EXCLUDED.user_id,
       email = COALESCE(EXCLUDED.email, stripe_customers.email)\`,
    [userId, stripeCustomerId, email ?? null]
  );
}

export async function getStripeCustomerForUser(userId: string): Promise<string | null> {
  const result = await query<{ stripe_customer_id: string }>(
    "SELECT stripe_customer_id FROM stripe_customers WHERE user_id = $1::uuid LIMIT 1",
    [userId]
  );
  return result.rows[0]?.stripe_customer_id ?? null;
}

export async function getStripeCustomerId(email: string): Promise<string | null> {
  const result = await query<{ stripe_customer_id: string }>(
    "SELECT stripe_customer_id FROM stripe_customers WHERE email = $1 LIMIT 1",
    [email]
  );
  return result.rows[0]?.stripe_customer_id ?? null;
}

export async function syncSubscriptionFromStripe(subscription: Stripe.Subscription) {
  const customerId = typeof subscription.customer === "string"
    ? subscription.customer
    : subscription.customer.id;
  const priceId = subscription.items.data[0]?.price?.id ?? null;
  const tier = subscription.metadata?.tier ?? null;

  await query(
    \`INSERT INTO subscriptions (stripe_subscription_id, stripe_customer_id, stripe_price_id, status, tier, current_period_end, cancel_at_period_end, updated_at)
     VALUES ($1, $2, $3, $4, $5, to_timestamp($6), $7, NOW())
     ON CONFLICT (stripe_subscription_id) DO UPDATE SET
       status = EXCLUDED.status,
       stripe_price_id = EXCLUDED.stripe_price_id,
       tier = EXCLUDED.tier,
       current_period_end = EXCLUDED.current_period_end,
       cancel_at_period_end = EXCLUDED.cancel_at_period_end,
       updated_at = NOW()\`,
    [
      subscription.id,
      customerId,
      priceId,
      subscription.status,
      tier,
      subscription.current_period_end,
      subscription.cancel_at_period_end,
    ]
  );
}

export async function recordWebhookEvent(event: Stripe.Event) {
  await query(
    \`INSERT INTO webhook_events (stripe_event_id, type, payload) VALUES ($1, $2, $3)
     ON CONFLICT (stripe_event_id) DO NOTHING\`,
    [event.id, event.type, JSON.stringify(event.data.object)]
  );
}
`;
}

export function validateDatabaseUrl(url: string | null): { valid: boolean; message: string } {
  if (!url) return { valid: false, message: "DATABASE_URL not configured" };
  if (!DATABASE_URL_PATTERN.test(url)) {
    return { valid: false, message: "DATABASE_URL format invalid (expected postgresql://...)" };
  }
  return { valid: true, message: "DATABASE_URL format valid" };
}

export async function testPostgresConnection(databaseUrl: string): Promise<{ ok: boolean; message: string }> {
  try {
    const pg = await import("pg");
    const pool = new pg.default.Pool({
      connectionString: databaseUrl,
      ssl: databaseUrl.includes("sslmode=require") || databaseUrl.includes("neon.tech")
        ? { rejectUnauthorized: false }
        : undefined,
      connectionTimeoutMillis: 8000,
    });
    const result = await pool.query("SELECT version()");
    await pool.end();
    const version = (result.rows[0] as { version: string }).version?.split(" ")[0] ?? "PostgreSQL";
    return { ok: true, message: `Connected (${version})` };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Connection failed";
    if (msg.includes("Cannot find package 'pg'")) {
      return { ok: false, message: "pg package not installed — run: npm install pg" };
    }
    return { ok: false, message: msg };
  }
}

export async function getDatabaseUrl(vault: SecretVault): Promise<string | null> {
  return (await vault.get("DATABASE_URL")) ?? (await vault.get("POSTGRES_URL")) ?? null;
}

export async function applyPostgresSchema(
  root: string,
  databaseUrl: string
): Promise<{ ok: boolean; message: string }> {
  try {
    const schemaPath = join(root, "db", "schema.sql");
    const sql = await readFile(schemaPath, "utf8");
    const pg = await import("pg");
    const pool = new pg.default.Pool({
      connectionString: databaseUrl,
      ssl: databaseUrl.includes("sslmode=require") || databaseUrl.includes("neon.tech") || databaseUrl.includes("supabase.co")
        ? { rejectUnauthorized: false }
        : undefined,
      connectionTimeoutMillis: 15000,
    });
    await pool.query(sql);
    await pool.end();
    return { ok: true, message: "Schema applied from db/schema.sql" };
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Schema apply failed";
    if (msg.includes("ENOENT")) {
      return { ok: false, message: "db/schema.sql not found — run deploy --generate first" };
    }
    return { ok: false, message: msg };
  }
}

export function postgresSetupGuide(provider: PostgresProvider): string {
  const guides: Record<PostgresProvider, string> = {
    neon: `# Neon PostgreSQL Setup
1. Create project at https://neon.tech
2. Copy connection string (pooled recommended for serverless)
3. Run: stripe-installer vault set DATABASE_URL "postgresql://..."
4. Apply schema: psql $DATABASE_URL -f db/schema.sql
`,
    supabase: `# Supabase PostgreSQL Setup
1. Create project at https://supabase.com
2. Settings → Database → Connection string (URI)
3. Run: stripe-installer vault set DATABASE_URL "postgresql://..."
4. Apply schema via SQL Editor or: psql $DATABASE_URL -f db/schema.sql
`,
    railway: `# Railway PostgreSQL Setup
1. railway add --plugin postgresql
2. Copy DATABASE_URL from Railway dashboard
3. Run: stripe-installer vault set DATABASE_URL "..."
4. Apply schema: railway run psql $DATABASE_URL -f db/schema.sql
`,
    render: `# Render PostgreSQL Setup
1. Create PostgreSQL instance in Render dashboard
2. Copy Internal/External Database URL
3. Add DATABASE_URL to environment variables
4. Apply schema: psql $DATABASE_URL -f db/schema.sql
`,
    "self-hosted": `# Self-hosted PostgreSQL
1. Ensure PostgreSQL 14+ is running
2. Create database: createdb myapp
3. stripe-installer vault set DATABASE_URL "postgresql://user:pass@host:5432/myapp"
4. psql $DATABASE_URL -f db/schema.sql
`,
    unknown: `# PostgreSQL Setup
1. Provision any PostgreSQL 14+ provider
2. stripe-installer vault set DATABASE_URL "postgresql://..."
3. psql $DATABASE_URL -f db/schema.sql
`,
  };
  return guides[provider];
}
