# Deployment & Stripe Automation Center

Combined platform for **deployment / API transfer** and **Stripe setup** — one login, one database, one encrypted vault per project.

This repo merges the former **Stripe Installer** and **API Transfer** products into a single Django + React app. Never exposes secrets to the frontend, AI, or logs.

| Doc | Purpose |
|-----|---------|
| [docs/STRUCTURE.md](docs/STRUCTURE.md) | Repo layout |
| [docs/AUTOMATION-CENTER.md](docs/AUTOMATION-CENTER.md) | Merge vision + secret rules |
| [docs/CUTOVER.md](docs/CUTOVER.md) | Retire old production apps |
| [docs/MERGE-STATUS.md](docs/MERGE-STATUS.md) | Cutover checklist (live) |
| [docs/RAILWAY.md](docs/RAILWAY.md) | Railway deploy + vault key |
| [docs/GO-LIVE.md](docs/GO-LIVE.md) | Client project → production |
| [docs/PRODUCTION.md](docs/PRODUCTION.md) | Docker prod stack |
| [backend/apps/api_transfer/README.md](backend/apps/api_transfer/README.md) | Transfer API reference |

---

## Production (Gilliom)

| Item | URL |
|------|-----|
| **Primary (custom domain)** | https://stripe-installer.gilliomfrontlinedigital.com/login |
| **Railway fallback** | https://stripe-installer-production.up.railway.app/login |
| **Health** | `GET /health/` |
| **SaaS billing webhook** | `POST /api/v1/billing/webhook/` |
| **Portfolio live demo** | [gilliomfrontlinedigital.com](https://gilliomfrontlinedigital.com) → **Deployment & Stripe Automation Center** card |
| **Railway service** | `Stripe-Installer` in project `hearty-enjoyment` |
| **Retiring** | `api-transfer-production` (legacy — delete after cutover) |

**Last verified** (local `python manage.py verify_cutover`):

| Check | Status |
|-------|--------|
| Unified health + vault | OK |
| SaaS billing configured | OK |
| Portfolio registry (`~/.stripe-installer/portfolio-registry.json`) | OK |
| Custom domain TLS | Pending — finish cert in Railway → Networking |
| Legacy api-transfer service | Still up — disable webhook, wait 48h, delete service |

```powershell
curl https://stripe-installer-production.up.railway.app/health/
cd backend; python manage.py verify_cutover
powershell -File scripts/complete-cutover.ps1
```

---

## What this replaces

| Old app | Was | Now |
|---------|-----|-----|
| Stripe Installer | `stripe-installer-production.up.railway.app` | Unified app (same service, expanded) |
| API Transfer | `api-transfer-production.up.railway.app` | `backend/apps/api_transfer/` module in this repo |

**Portfolio:** [gilliomfrontlinedigital.com](https://gilliomfrontlinedigital.com) is the marketing site only. Live demo buttons open product Railway URLs — not subdomains of the portfolio root.

---

## Status

**Complete** — Django + React product with agency, billing, API transfer, and production tooling.

| Area | Includes |
|------|----------|
| **Core** | Auth, projects, vault (import, rotation), scanner, pipeline, WebSocket logs, runs, diagnose/fix |
| **Stripe** | Verify, provision, codegen, `stripe.config.json` UI |
| **API Transfer** | Railway / Render / Fly deploy, GitHub import, Render→Railway migration, audit log, queue metrics |
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

**Optional:** charge for this platform itself via `SAAS_STRIPE_*` (or `STRIPE_*`) in Railway Variables / `backend/.env`.

The archived Node/Electron CLI in `legacy/node/` is reference only — **do not run it alongside Django on the same project.**

---

## Architecture

```
backend/          Django — vault, pipeline, stripe_engine, billing, deploy, api_transfer, ai, organizations
frontend/         React — dashboard, agency, vault UI, transfer panel, live pipeline terminal
legacy/node/      Archived Node CLI + Electron (reference only)
~/.stripe-installer/   Local vault master key, portfolio registry, per-project vault mirror (dev)
```

### One database, one vault

| Data | Stored | Exposed via API? |
|------|--------|------------------|
| Stripe keys, deploy tokens | AES-256-GCM in Postgres | **Never** — write-only, masked display only |
| Projects, runs, manifest | Django ORM | Yes (no secret values) |
| Scan / readiness | JSON on `Project` | Yes (sanitized) |

### Where deploy credentials live

Platform tokens (`RAILWAY_API_TOKEN`, `GITHUB_TOKEN`, `RENDER_*`, `FLY_API_TOKEN`) are stored **per project in the vault** — not as Railway service env vars. Optional server-level copies in Railway Variables enable live deploy without per-project setup. See [docs/CUTOVER.md](docs/CUTOVER.md).

### Vault master key (critical on Railway)

Project secrets are encrypted with scrypt + AES-GCM from **`VAULT_MASTER_KEY`**. If the key changes between deploys, stored secrets become undecryptable.

| Environment | Resolution |
|-------------|------------|
| **Railway** | `VAULT_MASTER_KEY` env wins (64-char hex) — see [docs/RAILWAY.md](docs/RAILWAY.md) |
| **Local dev** | `~/.stripe-installer/vault-master-key` (file first; env migrates to file) |

Generate once: `python -c "import secrets; print(secrets.token_hex(32))"`

---

## Quick start

```powershell
.\scripts\setup.ps1          # first time: venv, .env + vault key, migrate, npm
npm run dev                  # backend :8000 + frontend :5173
```

Open **http://127.0.0.1:5173** (API on `:8000`)

**Port already in use?**

```powershell
npm run dev:stop
npm run dev
```

---

## UI (after sign-in)

| Page | Route |
|------|--------|
| Projects dashboard | `/` |
| **Transfer / deploy hub** | `/deploy` — queue metrics, audit chain, migration controls |
| Project workspace | `/projects/{slug}` — vault, pipeline, runs, database, **Transfer panel**, AI, monitoring |
| Project settings | `/projects/{slug}/settings` — paths, git, org assignment, production URL |
| Agency | `/agency` — orgs, members, email invites, GitHub App, org projects |
| GitHub App callback | `/agency/github/callback` |
| Billing | `/billing` — personal + org subscriptions, deployment domain, license keys |

### Demo flow

**First run** — 3-step onboarding: GitHub → Stripe keys → create project.

**Project workspace:** readiness score, live pipeline, vault, AI copilot, diagnostics, codegen, deploy prep, **Transfer panel** (dry-run deploy, provider status), monitoring.

### Agency invites

1. **Agency** → invite by email (admin/owner).
2. **Existing user** — added immediately.
3. **New user** — `/register?invite=TOKEN` (email in prod, or copy link from pending invites).

Dev: invite emails print to the backend console (`EMAIL_BACKEND=console`).

---

## API Transfer module

Merged from the former API Transfer repo into `backend/apps/api_transfer/`.

**UI:** `/deploy` page + **Transfer** tab on each project.

**Worker** (queued Render→Railway migrations):

```powershell
npm run transfer:worker          # continuous
npm run transfer:worker:once     # one batch
```

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/transfer/status/` | Module status |
| GET | `/api/v1/transfer/providers/status/` | Railway / Render / GitHub / Fly readiness |
| GET | `/api/v1/transfer/runs/metrics/` | Queue counts |
| GET | `/api/v1/transfer/audit/` | Tamper-evident audit log |
| POST | `/api/v1/transfer/start/` | Start migration run |
| POST | `/api/v1/projects/{slug}/transfer/deploy/` | Full deploy pipeline |
| POST | `/api/v1/transfer/github/import/` | GitHub repo import |

Full route list: [backend/apps/api_transfer/README.md](backend/apps/api_transfer/README.md)

---

## Production deployment

### Railway (Gilliom production)

1. Attach **PostgreSQL** plugin → `DATABASE_URL` auto-set.
2. Set **`VAULT_MASTER_KEY`** (64-char hex) — pin once, never rotate without `rotate_vault_key`.
3. Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, Stripe keys (`STRIPE_*` or `SAAS_STRIPE_*`).
4. Custom domain: Railway → Networking → `stripe-installer.gilliomfrontlinedigital.com` (sets `RAILWAY_PUBLIC_DOMAIN`, drives `APP_PUBLIC_URL` + CORS).
5. Stripe webhook (live): `https://<your-domain>/api/v1/billing/webhook/`

Details: [docs/RAILWAY.md](docs/RAILWAY.md)

### Docker / self-hosted

```powershell
npm run build:frontend
npm run check:prod
npm run deploy:prod             # build + check + docker prod
```

Stack: Postgres, Redis, Daphne, Celery worker + Beat. Health: `GET /health/`.

---

## Portfolio registry (local machine)

Allowed apps for transfer/deploy linking live at:

```
~/.stripe-installer/portfolio-registry.json
```

Template in code: `backend/apps/stripe_installer/portfolio_registry.py` (`EXAMPLE_REGISTRY`).

Current production entry: **`automation-center`** → `https://stripe-installer.gilliomfrontlinedigital.com`

---

## Cutover (retire api-transfer-production)

Remaining manual steps — see [docs/MERGE-STATUS.md](docs/MERGE-STATUS.md):

1. Finish TLS on custom domain (Railway Networking).
2. Disable legacy Stripe webhook on `api-transfer-production.../api/billing/webhook`.
3. Smoke test: login → project → Transfer panel.
4. Redeploy portfolio (`frontlinedigital-1-production`) for updated demo URL.
5. After 48h quiet → delete `api-transfer-production` Railway service.

Helper: `powershell -File scripts/complete-cutover.ps1`

---

## License protection (deployed instances)

When you sell this platform as a product, deployed copies validate against your licensing server:

```env
STRIPE_INSTALLER_LICENSE_KEY=<from billing or email>
STRIPE_INSTALLER_DOMAIN=app.client.com
STRIPE_INSTALLER_VALIDATION_SERVER=https://your-licensing-server.com
LICENSE_ENFORCEMENT_ENABLED=true
LICENSE_ENFORCEMENT_MODE=readonly
```

Enforcement is **off by default**. See [backend/apps/licenses/README.md](backend/apps/licenses/README.md).

**Local dev test:**

```powershell
cd backend
python manage.py issue_dev_license --email you@test.com --domain localhost
```

---

## MCP (Cursor)

```powershell
# Copy .cursor/mcp.json.example → .cursor/mcp.json, set your email
cd backend
$env:STRIPE_INSTALLER_USER = "you@example.com"
python manage.py run_mcp_server
```

Tools: `list_projects`, `project_readiness`, `project_drift`, `project_diagnose`, `project_vault_status`, `start_pipeline`, `project_open_pr_prep`

See [docs/MCP.md](docs/MCP.md).

---

## API (base `/api/v1/`)

| Method | Path |
|--------|------|
| POST | `/auth/register/`, `/auth/login/` |
| GET | `/invites/{token}/` |
| GET/POST | `/organizations/`, `.../invite/`, `.../pending-invites/` |
| GET | `/agency/dashboard/` |
| GET/POST | `/projects/` |
| POST | `/projects/{slug}/vault/init/`, `.../vault/keys/set/`, `.../vault/import/` |
| POST | `/projects/{slug}/verify/`, `.../runs/`, `.../diagnose/`, `.../fix/` |
| POST | `/projects/{slug}/clone/`, `.../open-pr/`, `.../deploy/run/` |
| POST | `/projects/{slug}/transfer/deploy/` |
| GET | `/projects/{slug}/readiness/`, `.../audit/` |
| GET | `/transfer/providers/status/`, `/transfer/audit/`, `/transfer/runs/metrics/` |
| GET | `/billing/plans/`, `.../org/subscription/` |
| POST | `/billing/org/checkout/`, `/billing/webhook/` |
| POST | `/webhooks/github/` |
| POST | `/ci/readiness/` |
| POST | `/license/validate/` |
| WS | `/ws/runs/{run_id}/?token={jwt}` |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Dev environment

`backend/.env` (see `backend/.env.example`):

| Variable | Purpose |
|----------|---------|
| `VAULT_MASTER_KEY` | **Required** — 64 hex chars |
| `CELERY_EAGER=true` | Run pipeline in-process (no worker) |
| `CHANNEL_LAYER_INMEMORY=true` | WebSocket without Redis |
| `SAAS_STRIPE_*` / `STRIPE_*` | Platform billing (optional) |
| `GITHUB_APP_*` | GitHub App install + PR checks (optional) |
| `EMAIL_*` / `APP_PUBLIC_URL` | Org invite emails (optional) |
| `STRIPE_INSTALLER_*` / `LICENSE_ENFORCEMENT_*` | License protection (optional) |

Optional local platform tokens: copy `private_env/*.env.example` → `private_env/*.env` (gitignored). See [private_env/README.md](private_env/README.md).

---

## Verify

```powershell
npm run test
npm run smoke
npm run check:prod              # fails in dev mode — expected
cd frontend; npm run build
cd backend; python manage.py verify_cutover
```

---

## CLI

```powershell
cd backend
python manage.py stripe_installer run <project-slug>
python manage.py stripe_installer deploy <project-slug> --push
python manage.py rotate_vault_key --new-key <hex> --dry-run
python manage.py check_production
python manage.py verify_cutover
python manage.py issue_dev_license --email you@test.com --domain localhost
python manage.py validate_license_startup
python manage.py transfer_worker --once
```

---

## npm scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Backend + frontend |
| `npm run dev:stop` | Kill processes on ports 8000, 5173 |
| `npm run transfer:worker` | Process queued migration runs |
| `npm run transfer:worker:once` | One migration batch |
| `npm run docker:prod` | Docker Compose prod profile |
| `npm run deploy:prod` | Build frontend, check env, start Docker prod |
| `npm run check:prod` | Production env validation |

---

## Legacy Node CLI

The v0.6 CLI and Electron app live in [`legacy/node/`](legacy/node/README.md) for reference only.

---

## Repository

GitHub: [dallas8000-ops/Deployment-Stripe-center](https://github.com/dallas8000-ops/Deployment-Stripe-center)
