# Stripe Installer

AI-assisted Stripe setup that **never exposes secrets to AI or logs**. One Django + React product — encrypted vault, live pipeline, codegen, diagnose/fix, and deploy readiness.

## Status

**Complete** — Django + React product with agency, billing, and production tooling.

| Area | Includes |
|------|----------|
| **Core** | Auth, projects, vault (import, rotation), scanner, pipeline, WebSocket logs, runs, diagnose/fix |
| **Stripe** | Verify, provision, codegen, `stripe.config.json` UI |
| **Deploy** | Unified deploy prep, infra codegen, readiness report, manifest, platform push |
| **Database** | Neon, Supabase, Railway, Render, self-hosted provision + schema apply |
| **Git** | Clone (sync/async), private repo auth (token/SSH/credentials), GitHub PR |
| **Ops** | Docker prod stack, health checks, `check:prod`, `deploy:prod`, GitHub Actions CI, CLI |
| **AI copilot** | Fix copilot, NL→config, readiness coach, handoff pack, catalog strategist, webhook incident |
| **Monitoring** | Catalog drift (Celery Beat), webhook health, re-sync, audit log |
| **Environments** | Test / staging / production URLs in `deploy.config.json`, per-project selector |
| **Agency** | Organizations, RBAC, **email invites** (register link → auto-join), shared projects |
| **GitHub App** | Install flow + webhook — PR readiness checks and optional check runs |
| **CI gate** | Readiness gate API (`si_` keys), GitHub CI status, workflow template |
| **Org billing** | Per-org Stripe Checkout, free-tier limits, webhook sync, pipeline upgrade banners |
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

## UI (after sign-in)

| Page | Route |
|------|--------|
| Projects dashboard | `/` |
| Project workspace | `/projects/{slug}` — vault, pipeline, runs, database, deploy, AI, monitoring |
| Project settings | `/projects/{slug}/settings` — paths, git, org assignment, production URL |
| Agency | `/agency` — orgs, members, **email invites**, GitHub App, org projects |
| GitHub App callback | `/agency/github/callback` |
| Billing | `/billing` — personal + **organization** subscriptions |

### Agency invites

1. **Agency** → invite by email (admin/owner).
2. **Existing user** — added immediately.
3. **New user** — gets `/register?invite=TOKEN` (email in prod, or copy link from pending invites).
4. On register, they auto-join the org.

Dev: invite emails print to the **backend console** (`EMAIL_BACKEND=console`).

## Production

```powershell
npm run build:frontend
npm run check:prod              # validate .env before go-live
npm run deploy:prod             # build + check + docker prod
# or: npm run docker:prod
```

- Stack: Postgres, Redis, Daphne, Celery worker + **Beat** (drift checks)
- Health: `GET /health/` — database, vault, Redis, `frontend/dist`
- Docs: [docs/PRODUCTION.md](docs/PRODUCTION.md)

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
