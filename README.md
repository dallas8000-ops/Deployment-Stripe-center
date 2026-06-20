# Deployment & Stripe Automation Center

Combined platform for **deployment / API transfer** and **Stripe setup** — one login, one database, one encrypted vault per project.

- **Layout:** [docs/STRUCTURE.md](docs/STRUCTURE.md)
- **API Transfer merge:** [docs/AUTOMATION-CENTER.md](docs/AUTOMATION-CENTER.md)

Never exposes secrets to the frontend, AI, or logs.

## Status

**Complete** — Django + React product with agency, billing, and production tooling.

| Area | Includes |
|------|----------|
| **Core** | Auth, projects, vault (import, rotation), scanner, pipeline, WebSocket logs, runs, diagnose/fix |
| **Stripe** | Verify, provision, codegen, `stripe.config.json` UI |
| **Deploy** | Unified deploy prep, infra codegen, readiness report, manifest, platform push |
| **Database** | Neon, Supabase, Railway, self-hosted provision + schema apply |
| **Git** | Clone (sync/async), private repo auth (token/SSH/credentials), GitHub PR |
| **Ops** | Docker prod stack, health checks, `check:prod`, `deploy:prod`, GitHub Actions CI, CLI |
| **AI copilot** | Fix copilot, NL→config, readiness coach, handoff pack, catalog strategist, webhook incident |
| **Monitoring** | Catalog drift (Celery Beat), webhook health, re-sync, audit log |
| **Portfolio audit** | Account-wide webhook probe + local report (`~/.stripe-installer/reports/`) — [docs/PORTFOLIO-AUDIT.md](docs/PORTFOLIO-AUDIT.md) |
| **Environments** | Test / staging / production URLs in `deploy.config.json`, per-project selector |
| **Agency** | Organizations, RBAC, **email invites** (register link → auto-join), shared projects |
| **GitHub App** | Install flow + webhook — PR readiness checks and optional check runs |
| **CI gate** | Readiness gate API (`si_` keys), GitHub CI status, workflow template |
| **Org billing** | Per-org Stripe Checkout, free-tier limits, webhook sync, pipeline upgrade banners |
| **License protection** | Issue keys on SaaS checkout, instance validation, readonly/block enforcement for deployed copies |
| **MCP** | Cursor/stdio tools — projects, readiness, drift, vault status, pipeline, PR prep |

**Optional:** charge for Stripe Installer itself via `SAAS_STRIPE_*` in `backend/.env`.

The archived Node/Electron CLI in `legacy/node/` is reference only — **do not run it alongside Django on the same project.**

## Architecture

```
backend/          Django — vault, pipeline, stripe_engine, billing, deploy, ai, organizations
frontend/         React — dashboard, agency, vault UI, live pipeline terminal
legacy/node/      Archived Node CLI + Electron (reference only)
```

### One database, one vault

| Data | Stored | Exposed via API? |
|------|--------|------------------|
| Stripe keys | AES-256-GCM in Postgres/SQLite | **Never** — write-only, masked display only |
| Projects, runs, manifest | Django ORM | Yes (no secret values) |
| Scan / readiness | JSON on `Project` | Yes (sanitized) |

## Quick start

```powershell
.\scripts\setup.ps1          # first time: venv, .env + vault key, migrate, npm
npm run dev                  # backend :8000 + frontend :5173
```

Open **http://127.0.0.1:5173** (API on `:8000`)

**Go-live guide** (client project → production → agency → billing): [docs/GO-LIVE.md](docs/GO-LIVE.md)

**Port already in use?** Stop stale servers, then restart:

```powershell
npm run dev:stop
npm run dev
```

## Demo

**First run** — 3-step onboarding wizard guides new users through:
1. **GitHub Setup** — Connect repository for code generation
2. **Stripe Config** — Add API keys securely to vault
3. **Create Project** — See readiness dashboard light up in ~60 seconds

After onboarding, the **project workspace** shows:
- **Readiness Score** — 0–100 health indicator updated in real-time
- **Live Pipeline** — Stream events with auto-scroll and timestamps
- **Vault** — One-way secrets (never exposed in logs or frontend)
- **AI Copilot** — "Fix this" suggestions powered by LLM
- **Diagnostics** — Auto-scan for common Stripe misconfigs
- **Code Gen** — Download production-ready SDK (Node.js, Python, etc.)
- **Deploy Prep** — Readiness report, manifest, platform auto-detection
- **Monitoring** — Webhook health, drift detection, audit log

*Demo video + screenshots: [coming soon]*

## UI (after sign-in)

| Page | Route |
|------|--------|
| Projects dashboard | `/` |
| Project workspace | `/projects/{slug}` — vault, pipeline, runs, database, deploy, AI, monitoring |
| Project settings | `/projects/{slug}/settings` — paths, git, org assignment, production URL |
| Agency | `/agency` — orgs, members, **email invites**, GitHub App, org projects |
| GitHub App callback | `/agency/github/callback` |
| Billing | `/billing` — personal + **organization** subscriptions, deployment domain, license keys |

### Agency invites

1. **Agency** → invite by email (admin/owner).
2. **Existing user** — added immediately.
3. **New user** — gets `/register?invite=TOKEN` (email in prod, or copy link from pending invites).
4. On register, they auto-join the org.

Dev: invite emails print to the **backend console** (`EMAIL_BACKEND=console`).

### License protection (deployed instances)

When you sell Stripe Installer as a product ($79/mo model), deployed copies validate against **your** licensing server:

1. Customer subscribes on **Billing** with their deployment domain (e.g. `app.client.com`).
2. Stripe webhook issues a license key (also emailed).
3. Customer adds to `backend/.env` on their instance:

```env
STRIPE_INSTALLER_LICENSE_KEY=<from billing or email>
STRIPE_INSTALLER_DOMAIN=app.client.com
STRIPE_INSTALLER_VALIDATION_SERVER=https://your-licensing-server.com
LICENSE_ENFORCEMENT_ENABLED=true
LICENSE_ENFORCEMENT_MODE=readonly
```

4. Invalid/missing license → writes blocked (402) or full block (403). Docker startup validates before serving.

**Local dev test:**

```powershell
cd backend
python manage.py issue_dev_license --email you@test.com --domain localhost
# Add printed vars to .env, set LICENSE_ENFORCEMENT_ENABLED=true, restart
```

Enforcement is **off by default** (`LICENSE_ENFORCEMENT_ENABLED=false`). See [backend/apps/licenses/README.md](backend/apps/licenses/README.md).

## Production

```powershell
npm run build:frontend
npm run check:prod              # validate .env before go-live
npm run deploy:prod             # build + check + docker prod
# or: npm run docker:prod
```

- Stack: Postgres, Redis, Daphne, Celery worker + **Beat** (drift checks)
- Health: `GET /health/` — database, vault, Redis, `frontend/dist`
- Docs: [docs/PRODUCTION.md](docs/PRODUCTION.md) · [docs/RAILWAY.md](docs/RAILWAY.md) (single-service Railway deploy)

## MCP (Cursor)

```powershell
# Copy .cursor/mcp.json.example → .cursor/mcp.json, set your email
cd backend
$env:STRIPE_INSTALLER_USER = "you@example.com"
python manage.py run_mcp_server
```

Tools: `list_projects`, `project_readiness`, `project_drift`, `project_diagnose`, `project_vault_status`, `start_pipeline`, `project_open_pr_prep`

See [docs/MCP.md](docs/MCP.md).

## API (base `/api/v1/`)

| Method | Path |
|--------|------|
| POST | `/auth/register/`, `/auth/login/` |
| GET | `/invites/{token}/` — public invite preview |
| GET/POST | `/organizations/`, `.../invite/`, `.../pending-invites/` |
| GET | `/agency/dashboard/` |
| GET/POST | `/projects/` |
| POST | `/projects/{slug}/vault/init/`, `.../vault/keys/set/`, `.../vault/import/` |
| POST | `/projects/{slug}/verify/`, `.../runs/`, `.../diagnose/`, `.../fix/` |
| POST | `/projects/{slug}/clone/`, `.../open-pr/`, `.../deploy/run/` |
| GET | `/projects/{slug}/readiness/`, `.../audit/` |
| GET | `/billing/plans/`, `.../org/subscription/` |
| GET | `/license/me/` — authenticated user's license keys |
| POST | `/license/validate/` — instance heartbeat (deployed copies) |
| POST | `/billing/org/checkout/`, `/billing/webhook/` |
| POST | `/webhooks/github/` |
| POST | `/ci/readiness/` — CI gate (API key) |
| WS | `/ws/runs/{run_id}/?token={jwt}` |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Dev environment

`backend/.env` (see `backend/.env.example`):

| Variable | Purpose |
|----------|---------|
| `VAULT_MASTER_KEY` | **Required** — 64 hex chars |
| `CELERY_EAGER=true` | Run pipeline in-process (no worker) |
| `CHANNEL_LAYER_INMEMORY=true` | WebSocket without Redis |
| `SAAS_STRIPE_*` | Platform billing (optional) |
| `GITHUB_APP_*` | GitHub App install + PR checks (optional) |
| `EMAIL_*` / `APP_PUBLIC_URL` | Org invite emails (optional) |
| `STRIPE_INSTALLER_*` / `LICENSE_ENFORCEMENT_*` | License protection on deployed instances (optional) |

## Verify

```powershell
npm run test
npm run smoke
npm run check:prod          # fails in dev mode — expected
cd frontend; npm run build
```

## CLI

```powershell
cd backend
python manage.py stripe_installer run <project-slug>
python manage.py stripe_installer deploy <project-slug> --push
python manage.py rotate_vault_key --new-key <hex> --dry-run
python manage.py check_production
python manage.py issue_dev_license --email you@test.com --domain localhost
python manage.py validate_license_startup
```

## npm scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Backend + frontend (Node orchestrator) |
| `npm run dev:stop` | Kill processes on ports 8000, 5173 |
| `npm run docker:prod` | Docker Compose prod profile |
| `npm run deploy:prod` | Build frontend, check env, start Docker prod |
| `npm run check:prod` | Production env validation |

## Legacy Node CLI

The v0.6 CLI and Electron app live in [`legacy/node/`](legacy/node/README.md) for reference only.
