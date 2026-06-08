# Stripe Installer



AI-assisted Stripe setup that **never exposes secrets to AI or logs**. One Django + React product — encrypted vault, live pipeline, codegen, diagnose/fix, and deploy readiness.



## Status



**Complete** — all planned features for the Django + React product are implemented.



| Area | Includes |

|------|----------|

| **Core** | Auth, projects, vault (import, rotation), scanner, pipeline, WebSocket logs, runs, diagnose/fix |

| **Stripe** | Verify, provision, codegen, `stripe.config.json` UI |

| **Deploy** | Unified deploy prep, infra codegen, readiness report, manifest, platform push |

| **Database** | Neon, Supabase, Railway, Render, self-hosted provision + schema apply |

| **Git** | Clone (sync/async), private repo auth (token/SSH/credentials), GitHub PR |

| **Ops** | Production Docker stack, health checks, GitHub Actions CI, CLI (`stripe_installer`) |

| **AI copilot** | Fix copilot, NL→config, readiness coach, handoff pack, catalog strategist, webhook incident (paste or `evt_` fetch) |

| **Monitoring** | Catalog drift checks, webhook health, scheduled drift (Celery Beat), one-click re-sync, audit log |

| **Environments** | Test / staging / production URLs in `deploy.config.json`, active environment selector per project |

| **Agency** | Organizations, roles (owner/admin/member/viewer), shared project access, agency dashboard |

| **CI gate** | GitHub CI status, readiness gate API (`si_` keys), workflow template for Actions |

| **MCP** | `python manage.py run_mcp_server` — list projects, readiness, drift, diagnose via stdio |

| **GitHub App** | Webhook at `/api/v1/webhooks/github/` — PR readiness checks + optional check runs |

| **Org billing** | Subscribe per organization on Billing page (owner/admin) |



**Optional:** platform Billing page (`SAAS_STRIPE_*` in `.env`) — for charging users of Stripe Installer itself.



The archived Node/Electron CLI in `legacy/node/` is reference only — **do not run it alongside Django on the same project.**



## Architecture



```

backend/          Django — vault, pipeline, stripe_engine, billing, deploy, ai

frontend/         React — dashboard, vault UI, live pipeline terminal

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



**Go-live week** (real client → production → agency → billing): [docs/GO-LIVE.md](docs/GO-LIVE.md)



If `npm run dev` fails, run `.\scripts\setup.ps1` first, or use `.\scripts\dev.ps1` (opens two PowerShell windows).



**Port already in use?** Stop stale servers first:



```powershell

.\scripts\stop-dev.ps1

npm run dev

```



## Features



| Area | What it does |

|------|----------------|

| **Vault** | Write-only secrets, import `.env.local`, key rotation |

| **Scanner** | Detect framework, deps, existing Stripe code |

| **Pipeline** | Verify → provision → codegen → optional env sync → readiness |

| **WebSocket** | Live pipeline log stream in the browser |

| **Diagnose & fix** | Health scan + automated repairs |

| **Codegen** | Jinja2 templates — Django, Next.js, Express, Flask, and more |

| **Deploy** | Full deploy prep, Postgres (5 providers), infra codegen, platform push |

| **Git** | Clone, async clone, open GitHub PR with generated files |

| **AI** | Sanitized recommendations (Anthropic/OpenAI or local) |

| **Billing** | Optional — Stripe Installer subscriptions (`SAAS_STRIPE_*` env) |



### UI (after sign-in)



| Page | Route |

|------|--------|

| Projects dashboard | `/` |

| Project workspace | `/projects/{slug}` — vault, pipeline, runs, database, deploy files, AI |

| Project settings | `/projects/{slug}/settings` — local path, git URL, production URL |

| Billing | `/billing` — optional platform subscriptions |



## API (base `/api/v1/`)



| Method | Path |

|--------|------|

| POST | `/auth/register/`, `/auth/login/` |

| GET/POST | `/projects/` |

| POST | `/projects/{slug}/vault/init/`, `.../vault/keys/set/`, `.../vault/import/` |

| POST | `/projects/{slug}/verify/`, `.../runs/`, `.../diagnose/`, `.../fix/` |

| GET | `/projects/{slug}/readiness/`, `.../runs/{id}/download/` |

| GET | `/projects/{slug}/postgres/status/`, `.../schema/` |

| POST | `/projects/{slug}/postgres/provision/`, `.../apply-schema/`, `.../test/` |

| GET/PUT | `/projects/{slug}/deploy/config/`, `.../stripe/config/` |

| POST | `/projects/{slug}/deploy/run/`, `.../push/`, `.../infra/generate/` |

| POST | `/projects/{slug}/clone/`, `.../open-pr/` |

| GET | `/projects/{slug}/clone-status/` |

| PATCH | `/projects/{slug}/` |

| POST | `/projects/{slug}/ai/recommend/` |

| WS | `/ws/runs/{run_id}/?token={jwt}` |



See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/PRODUCTION.md`](docs/PRODUCTION.md).



## Dev environment



`backend/.env` (see `backend/.env.example`):



- `VAULT_MASTER_KEY` — **required**

- `CELERY_EAGER=true` + `CHANNEL_LAYER_INMEMORY=true` — no Redis/Celery needed locally



Production: `npm run docker:prod` — see [`docs/PRODUCTION.md`](docs/PRODUCTION.md).



## Verify



```powershell

npm run test

npm run smoke

cd frontend; npm run build

```



## CLI



```powershell

cd backend

python manage.py stripe_installer run <project-slug>

python manage.py stripe_installer deploy <project-slug> --push

python manage.py rotate_vault_key --new-key <hex> --dry-run

```



## Legacy Node CLI



The v0.6 CLI and Electron app live in [`legacy/node/`](legacy/node/README.md) for reference only.



## Roadmap



All items complete.



- [x] Neon/Supabase auto-provision

- [x] Railway/Render/self-hosted Postgres provision

- [x] One-click deploy prep pipeline

- [x] Platform push (Vercel/Railway/Render/Fly CLI)

- [x] stripe.config.json + deploy.config.json UI

- [x] Vault import + key rotation

- [x] Git clone (sync/async) + private repo auth + GitHub PR

- [x] Production Docker stack + CI

- [x] Django CLI parity (`stripe_installer`)


