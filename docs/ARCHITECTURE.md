# Stripe Installer — Architecture

**Django + React** product at repo root (`backend/`, `frontend/`). Legacy Node v0.6 CLI is archived under `legacy/node/`.

This document maps modules to Django apps, REST endpoints, and WebSocket events.

---

## Products

| Product | Runtime | Users |
|---------|---------|--------|
| **Stripe Installer** (this repo) | Django + React | Your paying clients (dev teams) |
| **Generated billing app** | Django/Next templates in *their* repo | *Their* end customers |

---

## Node → Django app mapping

| Node module | Django app | Responsibility |
|-------------|------------|----------------|
| `src/scanner/project-scanner.ts` | `apps/scanner/` | Detect framework, deps, Stripe features |
| `src/security/vault.ts` | `apps/vault/` | AES-256-GCM; DB-backed for SaaS |
| `src/security/sanitizer.ts` | `apps/ai/` + shared util | Redact secrets before AI/logs |
| `src/stripe/pipeline.ts` | `apps/stripe_engine/` | verify → provision → generate |
| `src/stripe/api-automation.ts` | `apps/stripe_engine/provision.py` | Products, prices, webhooks, portal |
| `src/stripe/code-generator.ts` | `apps/stripe_engine/codegen/` | Jinja2 templates per framework |
| `src/stripe/django-templates.ts` | `codegen/templates/django/` | Client billing output |
| `src/stripe/django-db-sync.ts` | `codegen/templates/django/db.py` | Customer/subscription DB sync |
| `src/stripe/django-connect.ts` | `codegen/templates/django/connect/` | Connect onboarding + transfers |
| `src/stripe/diagnostics.ts` | `apps/stripe_engine/diagnostics.py` | Issue detection |
| `src/stripe/repair.ts` | `apps/stripe_engine/repair.py` | Auto-fix actions |
| `src/deploy/deploy-pipeline.ts` | `apps/deploy/` | Infra, readiness, postgres |
| `src/deploy/postgres.ts` | `apps/deploy/postgres.py` | Schema, provision Neon/Supabase |
| `src/ai/orchestrator.ts` | `apps/ai/` | OpenAI/Anthropic with boundary |
| `src/cli.ts` | `apps/core/management/commands/` | CLI parity (optional) |
| `src/gui/installer-service.ts` | DRF viewsets + React | Replaces Electron |

---

## Installer SaaS — REST API (DRF)

Base: `/api/v1/`. Auth: session cookie or token. **Never return vault secret values.**

### Accounts (`apps/accounts/`)

| Method | Path | Maps from |
|--------|------|-----------|
| POST | `/auth/register/` | — |
| POST | `/auth/login/` | — |
| POST | `/auth/logout/` | — |
| GET | `/me/` | GUI user context |

### Projects (`apps/projects/`)

| Method | Path | Maps from |
|--------|------|-----------|
| GET | `/projects/` | GUI project list |
| POST | `/projects/` | `scan` target registration (git URL or path) |
| GET | `/projects/{id}/` | `status` |
| POST | `/projects/{id}/scan/` | `ProjectScanner.scan()` |
| GET | `/projects/{id}/profile/` | `ScanSummary.profile` |

### Vault (`apps/vault/`)

| Method | Path | Maps from |
|--------|------|-----------|
| POST | `/projects/{id}/vault/init/` | `vault init` |
| POST | `/projects/{id}/vault/keys/` | `vault set` (body: key, value) |
| GET | `/projects/{id}/vault/keys/` | `vault list` (names only) |
| POST | `/projects/{id}/vault/import/` | `vault import` |

### Stripe engine (`apps/stripe_engine/`)

| Method | Path | Maps from |
|--------|------|-----------|
| POST | `/projects/{id}/verify/` | `verify` |
| POST | `/projects/{id}/runs/` | `run` / `automate` (starts async job) |
| GET | `/projects/{id}/runs/{run_id}/` | Run status + summary |
| GET | `/projects/{id}/manifest/` | `.stripe-installer/stripe-manifest.json` |
| POST | `/projects/{id}/diagnose/` | `diagnose` |
| POST | `/projects/{id}/fix/` | `fix --all` / `--action` |
| GET | `/projects/{id}/readiness/` | `readiness` |

### Deploy (`apps/deploy/`)

| Method | Path | Maps from |
|--------|------|-----------|
| POST | `/projects/{id}/deploy/` | `deploy` |
| POST | `/projects/{id}/postgres/provision/` | `postgres provision` |
| POST | `/projects/{id}/postgres/apply-schema/` | `postgres apply-schema` |

### AI (`apps/ai/`)

| Method | Path | Maps from |
|--------|------|-----------|
| POST | `/projects/{id}/ai/recommend/` | `setup --ai` |

---

## Real-time — Channels WebSocket

URL: `ws://app/ws/runs/{run_id}/`

Event payload matches `src/stripe/pipeline-events.ts` (used today by Electron `pipeline-event` IPC):

```typescript
interface PipelineEvent {
  step: string;       // e.g. verify.keys, provision.products, generate.file
  status: "running" | "ok" | "failed" | "detail";
  message: string;
  detail?: boolean;   // indent in UI
  score?: number;     // on run.completed
}
```

### Example sequence (Run full setup)

| Icon | Message |
|------|---------|
| ✓ | Vault unlocked |
| ✓ | API keys verified (live mode) |
| ⏳ | Provisioning Stripe products… |
| → | Created: Pro Monthly ($19/mo) |
| ✓ | Products provisioned |
| ⏳ | Registering webhooks… |
| ✓ | Webhook registered: https://… |
| ⏳ | Generating code… |
| → | stripe/views.py |
| ✓ | Code generated (N files) |
| ⏳ | Syncing .env.local… |
| ✓ | Done — Readiness Score: 87/100 |

### React hook (SaaS frontend)

```tsx
function usePipelineRun(runId: string | null) {
  const [lines, setLines] = useState<PipelineEvent[]>([]);
  useEffect(() => {
    if (!runId) return;
    const ws = new WebSocket(`${WS_BASE}/ws/runs/${runId}/`);
    ws.onmessage = (msg) => {
      const data = JSON.parse(msg.data) as PipelineWsMessage;
      if (data.type === "pipeline.event") setLines((l) => [...l, data.event]);
    };
    return () => ws.close();
  }, [runId]);
  return lines;
}
```

Electron desktop implements the same UX today via `runPipelineStream` + `#pipeline-terminal`.

| Event | When | Payload |
|-------|------|---------|
| `run.started` | Job queued | `{ runId, projectId }` |
| `verify.keys` | | `{ status: running\|ok\|failed }` |
| `provision.products` | Stripe API | `{ status, productId? }` |
| `provision.prices` | | `{ status, count? }` |
| `provision.webhook` | | `{ status, url? }` |
| `generate.files` | Codegen | `{ path, action }` |
| `deploy.readiness` | | `{ score, categories[] }` |
| `run.completed` | | `{ summary, nextSteps[] }` |
| `run.failed` | | `{ error }` (sanitized) |

Maps from CLI `ora` spinners in `cli.ts` and pipeline steps in `pipeline.ts` / `deploy-pipeline.ts`.

---

## Generated client site — Django billing methods (deterministic)

Output from `stripe-installer fix … --action generate-files` on a Django project.

### HTTP views (`stripe/views.py`)

| View | Method | URL name | Purpose |
|------|--------|----------|---------|
| `pricing` | GET | `stripe-pricing` | Server-rendered plans |
| `checkout` | POST | `stripe-checkout` | Create Checkout Session → redirect |
| `success` | GET | `stripe-success` | Retrieve session; session + DB link |
| `account` | GET | `stripe-account` | Portal entry (DB → session fallback) |
| `portal` | POST | `stripe-portal` | Billing Portal (update payment method) |
| `webhook` | POST | `stripe-webhook` | Signature verify → `dispatch_stripe_event` |
| `stripe_me` | GET | `stripe-me` | JSON customer + subscription lookup |
| `session_info` | POST | `stripe-session` | Optional API session lookup |

### DB module (`stripe/db.py`)

| Function | Trigger | Writes / reads |
|----------|---------|----------------|
| `link_customer_from_checkout(session)` | `checkout.session.completed` | `stripe_customers.auth_user_id` |
| `sync_subscription_from_stripe(sub)` | `customer.subscription.*` | `subscriptions` |
| `get_stripe_customer_for_user(pk)` | account, portal, me | **Deterministic** customer ID |
| `get_active_subscription_for_customer(id)` | me | Active/trialing sub |
| `record_webhook_event(event)` | All webhooks | Idempotency log |
| `sync_connect_account(account)` | `account.updated` | `stripe_connect_accounts` |
| `get_connect_account_for_user(pk)` | Connect views | Connected account ID |
| `record_transfer(transfer)` | `transfer.*` | `stripe_transfers` |

### Webhook dispatch (`stripe/webhook_handlers.py`)

| Stripe event | Handler |
|--------------|---------|
| `checkout.session.completed` | `link_customer_from_checkout` |
| `customer.subscription.created/updated/deleted` | `sync_subscription_from_stripe` |
| `invoice.payment_failed` | Hook point (email, dunning) |
| `account.updated` | `sync_connect_account` |
| `transfer.created/updated/reversed` | `record_transfer` |

### Scheduled payments flow

1. User POSTs checkout → Stripe saves **payment method** on **Customer**.
2. Webhook links `auth_user_id` = `User.pk`.
3. Stripe charges on schedule (subscription); `invoice.paid` / `invoice.payment_failed` fire.
4. App checks entitlements via `subscriptions.status` — not localStorage.

---

## Stripe Connect — transfers (generated client site)

| View | Method | URL | Purpose |
|------|--------|-----|---------|
| `connect_onboard` | GET | `/stripe/connect/onboard/` | Express AccountLink |
| `connect_return` | GET | `/stripe/connect/return/` | Post-onboarding |
| `connect_dashboard` | GET | `/stripe/connect/dashboard/` | Express Dashboard login |
| `connect_transfer` | POST | `/stripe/connect/transfer/` | `Transfer.create` (staff) |

Platform API: `stripe.Transfer.create(amount, currency, destination=acct_…)`.

Docs: `docs/STRIPE-CONNECT.md` in generated projects.

---

## Database schema (`db/schema.sql`)

| Table | Purpose |
|-------|---------|
| `stripe_customers` | `auth_user_id` (Django pk), `stripe_customer_id` |
| `subscriptions` | Scheduled billing state from webhooks |
| `webhook_events` | Idempotency / audit |
| `stripe_connect_accounts` | Express accounts per user |
| `stripe_transfers` | Transfer log |

Apply: `psql $DATABASE_URL -f db/schema.sql`

---

## Codegen source files (for Jinja2 port)

When porting to `apps/stripe_engine/codegen/templates/`:

| Framework | Node source |
|-----------|-------------|
| Django | `django-templates.ts`, `django-db-sync.ts`, `django-connect.ts`, `code-generator.ts` (djangoViews) |
| Next.js App | `code-generator.ts` (webhookRouteApp, pricingPage, …) |
| Express/Fastify | `code-generator.ts` + `ui-generators.ts` (vanillaPublicUi) |
| Remix/Nuxt/SvelteKit | `ui-generators.ts` |
| Flask/Rails/Laravel | `code-generator.ts` + `ui-generators.ts` |
| Shared Node lib | `code-generator.ts` (stripeClient, webhookDispatcher) |
| Postgres sync (JS) | `deploy/postgres.ts` (postgresWebhookSync) |

Dump examples: `stripe-installer fix <fixture> --action generate-files` on each framework fixture.

---

## Security rules (both products)

1. Secret keys only in vault / server env — never React, never AI prompts.
2. Webhook handlers always verify `Stripe-Signature`.
3. SaaS vault: encrypt at rest; list keys without values.
4. Connect transfers: server-side only; default `@staff` on `connect_transfer`.
5. Generated billing: form POST + CSRF — no SPA localStorage for customer ID.

---

## Suggested build order

1. `projects` + `runs` + Channels (mock pipeline UI)
2. Port `vault` + `verify` + `provision` (stripe_engine)
3. Jinja2 codegen — **Django client output first** (already in TS)
4. Git clone in worker → generate → zip/PR
5. Connect + transfer views in generated output (done in TS; test on client project)
6. DRF + React dashboard consuming `/api/v1/` + WebSocket

---

## Related docs (generated Django projects)

- `docs/STRIPE-DJANGO.md` — setup, DB, scheduled payments
- `docs/STRIPE-AUTH.md` — auth_user_id linking
- `docs/STRIPE-CONNECT.md` — onboarding + transfers
