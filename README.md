# Stripe Installer

AI-assisted Stripe setup that **never exposes secrets to AI or logs**. The app scans your project, determines what Stripe integration you need, and automates boilerplate — while keeping API keys in an encrypted local vault.

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Project Scan   │────▶│  Sanitized       │────▶│  AI Layer       │
│  (files/deps)   │     │  Context Only    │     │  (no secrets)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                                                │
         ▼                                                ▼
┌─────────────────┐                              ┌─────────────────┐
│  Encrypted      │◀──── secrets stay here ──────│  Stripe Setup   │
│  Vault (.enc)   │                              │  Engine         │
└─────────────────┘                              └─────────────────┘
```

### Security Boundary

| Data | AI sees it? | Logs? | Committed to git? |
|------|-------------|-------|-------------------|
| API keys | Never | Never | Never |
| Vault contents | Never | Never | Never (`.stripe-installer/` is gitignored) |
| Framework, deps, file structure | Yes (sanitized) | Yes | N/A |
| `.env.example` placeholders | Yes | Yes | Yes (safe) |

## Quick Start

```bash
npm install
npm run dev -- scan ./your-project
```

### 1. Initialize the vault

```bash
npm run dev -- vault init
```

### 2. Store secrets (encrypted, local only)

```bash
npm run dev -- vault set STRIPE_SECRET_KEY sk_test_...
npm run dev -- vault set STRIPE_PUBLISHABLE_KEY pk_test_...
npm run dev -- vault set STRIPE_WEBHOOK_SECRET whsec_...
```

### 3. Scan your project

```bash
npm run dev -- scan ./your-project
```

Detects framework (Next.js, Express, React, etc.), existing Stripe code, env files, and suggests features.

### 4. Verify API keys

```bash
npm run dev -- verify ./your-project
```

Validates secret + publishable key format, mode matching, and live API connectivity.

### 5. One-command full setup

```bash
cp stripe.config.example.json ./your-project/stripe.config.json
npm run dev -- run ./your-project --sync-env
```

Runs: verify keys → provision products/prices/webhooks/portal → generate code → sync `.env.local`.

### 6. Full Stripe automation (API + code)

```bash
npm run dev -- automate ./your-project --provision --generate
```

| Action | Implementation |
|--------|----------------|
| Create products | Stripe Products API (idempotent — reuses existing) |
| Create pricing tiers | Stripe Prices API with monthly/yearly + trial support |
| Configure subscriptions | Recurring prices + Billing Portal Configuration |
| Register webhook endpoints | Webhook Endpoints API + event dispatcher module |
| Generate checkout pages | Pricing page, CheckoutButton, checkout API route |
| Generate billing portal | Portal route + ManageSubscriptionButton + account page |
| Verify API keys | Format, mode match, balance + account capabilities |

Improvements in v0.2:
- **Idempotent provisioning** — re-runs reuse existing products/prices from manifest
- **Trial periods** — `trialDays` per tier in config
- **Webhook dispatcher** — `lib/stripe-webhooks.ts` with extensible event handlers
- **Success + account pages** — post-checkout and subscription management UI
- **App/pages router** — auto-detects Next.js router and generates correct paths
- **Vault import** — `vault import` pulls keys from `.env.local` into encrypted vault
- **Unified pipeline** — `run` command does everything in one step

### 6. Run setup (code only)

```bash
npm run dev -- setup ./your-project --apply --validate
```

Generates webhook handlers, checkout routes, `lib/stripe.ts`, and `.env.example`.

### 7. Optional: AI recommendations

```bash
npm run dev -- vault set OPENAI_API_KEY sk-...
npm run dev -- setup ./your-project --ai
```

AI receives only sanitized context — secret values are redacted before any prompt is built.

## Commands

| Command | Description |
|---------|-------------|
| `scan [path]` | Analyze project structure and Stripe needs |
| `vault init` | Create encrypted vault |
| `vault set <key> <value>` | Store a secret |
| `vault list` | List stored key names (not values) |
| `setup [path]` | Generate setup plan |
| `setup --apply` | Write boilerplate files |
| `setup --validate` | Test Stripe API with vault key |
| `setup --ai` | Get AI-powered recommendations |
| `verify` | Verify secret + publishable API keys |
| `status` | Show manifest, vault, and project Stripe state |
| `run` | Full pipeline: verify → provision → generate |
| `sync-env` | Write vault secrets to `.env.local` |
| `vault import` | Import keys from `.env.local` into vault |
| `automate --provision` | Create products, prices, webhooks, portal via Stripe API |
| `automate --generate` | Generate checkout, webhook, and billing portal code |
| `automate --force` | Overwrite existing generated files |
| `deploy` | One-click: Stripe + PostgreSQL + monitoring + backup + readiness |
| `deploy --provision-db` | Auto-create Neon/Supabase database via API |
| `readiness` | Production readiness score (0–100) across 8 categories |
| `postgres provision` | Create Neon/Supabase DB, store DATABASE_URL, apply schema |
| `postgres apply-schema` | Apply `db/schema.sql` to vault DATABASE_URL |
| `postgres status` | Show DB connection and provision manifest |
| `diagnose` | Find Stripe setup issues (credentials, files, webhooks, catalog) |
| `fix --all` | Auto-repair all fixable issues |
| `fix --issue <id>` | Fix a specific diagnosed issue |

## What It Detects

- **Frameworks**: Next.js, React, Express, Fastify, Remix, Nuxt, SvelteKit, Django, Flask, Rails, Laravel
- **Stripe features**: Checkout, subscriptions, webhooks, billing portal, payment intents
- **Secrets in files**: Redacts `sk_*`, `pk_*`, `whsec_*`, and generic API keys before any AI call

### Framework coverage

| Stack | Code generation | Diagnose |
|-------|-----------------|----------|
| Next.js (App + Pages router) | **Full** | Framework-aware file checks |
| Express / Fastify | **Full** — API + static billing pages | Webhook + page checks |
| Remix / Nuxt / SvelteKit | **Full** — API routes + pricing/account UI | Signature + file checks |
| React (SPA) | **Full** — pages, components, dev API server | Proxy + backend guidance |
| Django / Flask | **Full** — views, templates, URLs | Python webhook checks |
| Rails / Laravel | **Full** — controller, views, routes | Manual route wiring docs |
| Unknown stack | **Minimal** — generic client + wiring guide | Generic checks |

Run `stripe-installer scan` to see framework-specific recommendations for your project.

## Architecture

- `src/scanner/` — Reads project files, detects stack and needs
- `src/security/vault.ts` — AES-256-GCM encrypted local storage
- `src/security/sanitizer.ts` — Redacts secrets; blocks unsafe AI submissions
- `src/stripe/setup-engine.ts` — Plans and generates Stripe integration code
- `src/stripe/api-automation.ts` — Provisions products, prices, webhooks, billing portal
- `src/stripe/code-generator.ts` — Checkout pages, webhook handlers, portal routes
- `src/deploy/framework-deploy.ts` — Per-framework health checks, Dockerfiles, deploy paths
- `src/stripe/framework-profiles.ts` — Per-framework codegen level, webhook paths, diagnostics
- `src/stripe/session-routes.ts` — Post-checkout session lookup for customer linking
- `src/ai/orchestrator.ts` — AI layer with enforced secrets boundary

## Stripe API References

- [Stripe API Documentation](https://docs.stripe.com/api)
- [Stripe Billing Documentation](https://docs.stripe.com/billing)

## Production Deployment (v0.3)

One command sets up everything for production:

```bash
cp deploy.config.example.json ./your-app/deploy.config.json
# Edit domain, productionUrl, platform

npm run dev -- deploy ./your-app --force
```

| Feature | What it does |
|---------|-------------|
| **One-click deploy** | `deploy` — Stripe + infra + readiness in one pipeline |
| **Stripe setup** | Provisions live products, webhooks, portal (from v0.2) |
| **PostgreSQL** | Schema, `lib/db.ts`, webhook sync, Neon/Supabase/Railway guides |
| **Domain setup** | `deploy/DNS-SSL-SETUP.md` with DNS records per platform |
| **SSL setup** | Auto on Vercel/Railway/Render; verification via readiness checks |
| **Monitoring** | `/api/health` endpoint with DB check; optional Sentry stub |
| **Backup setup** | `scripts/backup-db.sh` + `.ps1` with retention pruning |
| **Readiness checks** | `readiness` — scores 0–100 across 8 categories |

### Readiness categories
Stripe · Database · Domain · SSL · Security · Monitoring · Backup · Deploy

```bash
npm run dev -- readiness ./your-app   # check without generating files
```

### PostgreSQL quick start
```bash
# Option A: Auto-provision via API (v0.4)
npm run dev -- vault set NEON_API_KEY napi_...
npm run dev -- postgres provision ./your-app --provider neon

# Option B: Manual
npm run dev -- vault set DATABASE_URL "postgresql://..."
npm run dev -- postgres apply-schema ./your-app

npm run dev -- readiness ./your-app
```

## PostgreSQL Auto-Provisioning (v0.4)

Create a Neon or Supabase database via API — connection string stored in vault, schema applied automatically.

```bash
# Neon
npm run dev -- vault set NEON_API_KEY napi_...
npm run dev -- postgres provision ./your-app --provider neon --region aws-us-east-1

# Supabase
npm run dev -- vault set SUPABASE_ACCESS_TOKEN sbp_...
npm run dev -- vault set SUPABASE_ORG_ID your-org-id
npm run dev -- postgres provision ./your-app --provider supabase
```

Or enable in `deploy.config.json`:
```json
"postgres": { "provider": "neon", "autoProvision": true }
```

Then: `npm run dev -- deploy ./your-app --provision-db --force`

### Webhook → database sync
Generated `lib/stripe-webhooks.ts` now syncs subscriptions to PostgreSQL when `DATABASE_URL` is set (uses `lib/stripe-db.ts` from deploy).

### Anthropic AI support
```bash
npm run dev -- vault set ANTHROPIC_API_KEY sk-ant-...
npm run dev -- setup ./your-app --ai
```
Uses Anthropic if key is present, otherwise OpenAI, otherwise local recommendations.

## Diagnose & Fix

Scan a project for Stripe problems and repair them automatically:

```bash
npm run dev -- diagnose ./your-app
npm run dev -- fix ./your-app --all
npm run dev -- fix ./your-app --issue missing-webhook-secret
```

**Checks:** vault credentials, API key validity, missing files, webhook registration, product catalog, env sync, secrets in source, `.gitignore`

**Auto-fixes:** import env → vault, sync vault → `.env.local`, generate missing files, provision catalog/webhook, fix `.gitignore`, create `stripe.config.json`

The **Diagnose & Fix** tab in the desktop app provides the same workflow with one-click repair.

## Desktop GUI (v0.5)

Launch the Electron app for a visual workflow — same secure vault boundary as the CLI.

```bash
npm install
npm run gui
```

| Screen | What you can do |
|--------|-----------------|
| **Dashboard** | Browse project, scan, view framework & recommendations |
| **Diagnose & Fix** | Find Stripe issues and apply automated repairs |
| **Vault** | Create/unlock vault, store secrets (values never shown again) |
| **Stripe Setup** | Verify keys, run full provision + code generation pipeline |
| **Deploy** | One-click deploy, PostgreSQL provision, infra generation |
| **Readiness** | Production score across 8 categories |

Secrets are handled only in the main process — the renderer never receives decrypted values.

## Roadmap

- [ ] Electron app packaging (Windows/macOS installers)
- [ ] Support for Stripe Connect onboarding
- [ ] Diff-based apply (modify existing files safely)
