# Deployment & Stripe Automation Center

One platform for **deploy/migrate apps** (API Transfer) and **Stripe setup** (Stripe Installer). Stripe Installer is the **base repo**; API Transfer merges in as a feature module.

## Vision

```
Deployment & Stripe Automation Center
├── Dashboard / Projects
├── Secret vault (encrypted, per project)
├── API Transfer      → Railway, Render, Fly, env sync, GitHub import
├── Stripe Installer  → products, webhooks, codegen, diagnose
├── Readiness & diagnostics
└── Audit logs
```

One **Project** record holds everything:

```
Project
 ├── GitHub repo / local path
 ├── Platform (Railway, Render, …)
 ├── Vault secrets (STRIPE_*, RAILWAY_*, GITHUB_*, …)
 ├── Stripe catalog / webhooks
 ├── Deployment history
 └── Generated code / run logs
```

## Current repo mapping

| Your plan | This repo today |
|-----------|-----------------|
| `automation-center/backend/apps/projects/` | `backend/apps/projects/` |
| `automation-center/backend/apps/vault/` | `backend/apps/vault/` |
| `automation-center/backend/apps/users/` | `backend/apps/accounts/` + `organizations/` |
| `stripe_installer/` | `backend/apps/stripe_engine/` (+ `billing/`) |
| `api_transfer/` | `backend/apps/api_transfer/` (stub — code migrating from `API Transfer` repo) |
| `deploy_transfer/` | Partially `backend/apps/deploy/` |

## Secret handling rules

| Layer | What | Never |
|-------|------|--------|
| **Frontend** | Buttons, status, masked key names | Receive or display secret values |
| **Backend** | Decrypt vault, call Stripe/Railway/GitHub | Log secrets |
| **Database** | AES-256-GCM vault per project | Plaintext secrets |
| **Local dev** | `private_env/*.env` (gitignored) | Commit or push to GitHub |
| **Per-user projects** | Vault table | `Project1.env`, `Project2.env` on disk |

Cross-module access (no frontend hop):

```python
from apps.vault.services import get_project_secret

stripe_key = get_project_secret(project, "STRIPE_SECRET_KEY")
railway_token = get_project_secret(project, "RAILWAY_API_TOKEN")
```

## Local `private_env/` (your machine only)

```
private_env/
├── stripe.env.example   → copy to stripe.env
├── railway.env.example
├── render.env.example
└── github.env.example
```

Loaded at startup after `backend/.env`. See `private_env/README.md`.

Production SaaS keys also persist under `~/.stripe-installer/` (installer app secrets + per-project vault backup).

## Safe migration order

Work on branch `merge-api-transfer-stripe` (do not merge to production until tested).

1. **Stripe Installer stays the Django host** — already has projects, vault, orgs, deploy.
2. **Add `private_env/` + vault service facade** — done.
3. **Stub `apps.api_transfer`** — status endpoint at `GET /api/v1/transfer/status/`.
4. **Migrate API Transfer `migrationengine`** views/services into `apps.api_transfer` one slice at a time.
5. **Unify models**: map API Transfer `Workspace` → `Organization`; deployment runs → shared `runs` or new `api_transfer` models linked to `Project`.
6. **Merge frontends**: React features under `frontend/src/features/transfer/` and `features/stripe/`.
7. **One sidebar**: Projects → Deploy → Stripe → Diagnostics → Settings.
8. **Delete duplicate** login/billing only after parity tests.

## Before merging code

Search both repos for leaked secrets:

```
sk_live_  sk_test_  whsec_  ghp_  railway  render  token  secret  apikey
```

Remove hardcoded values; store in vault or `private_env/` locally.

## API Transfer source

Local path (typical): `C:\Software Projects\API Transfer`

Key packages to port:

- `migrationengine/` — Railway/Render deploy, transfer runs, env backup
- `deployments/` — secure deploy hydration
- `core/` — platform setup, RBAC, env file merge

## Related docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — Stripe Installer API surface
- [GO-LIVE.md](GO-LIVE.md) — production checklist
- `backend/apps/api_transfer/README.md` — module notes for developers
