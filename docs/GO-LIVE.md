# Go-live week — real client → production → agency → billing

Five-day runbook for taking Stripe Installer from dev to a hosted agency product with one real client project.

Replace `installer.yourdomain.com` with your public URL throughout.

---

## Days 1–2 — Real client project

**Goal:** One client repo passes vault → full setup → readiness.

### Prerequisites

- Client GitHub repo URL (or local path on your machine)
- Stripe **test** keys from the client's Stripe Dashboard (Developers → API keys)
- Optional: `GITHUB_TOKEN` with `repo` scope for private clones and PRs

### Step-by-step

| # | Action | Where in UI |
|---|--------|-------------|
| 1 | Register / log in | `/register` or `/login` |
| 2 | **Create project** — name, Git URL | Projects (`/`) |
| 3 | **Settings** → clone repo (or set local path) | `/projects/{slug}/settings` |
| 4 | **Unlock vault** | Project page → Secure vault |
| 5 | Store keys (write-only) | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` |
| 6 | Optional: `GITHUB_TOKEN` in vault | For private repo + Open PR |
| 7 | Set **Production app URL** | Settings → production URL (client's app, not installer) |
| 8 | Edit **stripe.config.json** | Project page → Stripe config (tiers, app URL) |
| 9 | Edit **deploy.config.json** | Project page → Deploy config (platform, env URLs) |
| 10 | **Run full setup** | Project page → pipeline options → Run full setup |
| 11 | **Readiness** | Score ≥ 80 is a good target before client handoff |
| 12 | **Deploy prep** | Generates manifest, syncs env, optional Postgres |
| 13 | Optional: **Open GitHub PR** | Requires vault token + uncommitted generated files |

### CLI alternative (same backend)

```powershell
cd backend
.venv\Scripts\python.exe manage.py stripe_installer run <project-slug>
.venv\Scripts\python.exe manage.py stripe_installer deploy <project-slug>
```

### Day 1–2 checklist

- [ ] Project clones or local path scans successfully
- [ ] Vault initialized; Stripe keys verify (Verify keys button)
- [ ] Full setup completes without `run.failed` in terminal
- [ ] Readiness report shows no critical failures
- [ ] Client webhook URL documented (in **their** app, not installer)
- [ ] Test vs live keys consistent everywhere

### Common issues

| Symptom | Fix |
|---------|-----|
| Clone fails | `GITHUB_TOKEN` in vault, or `GIT_SSH_KEY_PATH` in server `.env` |
| Pipeline stuck | Dev: `CELERY_EAGER=true` OK; prod: Celery worker must run |
| Readiness low | Run **Diagnose** → fix issues or use AI fix copilot |
| No AI features | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in **project** vault |

---

## Day 3 — Production hosting

**Goal:** Installer runs at `https://installer.yourdomain.com` with Postgres, Redis, Celery, Beat.

See also [PRODUCTION.md](./PRODUCTION.md).

### Generate secrets

```powershell
python -c "import secrets; print('VAULT_MASTER_KEY=' + secrets.token_hex(32))"
python -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50))"
```

### Production `.env` (minimum)

```env
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<from above>
DJANGO_ALLOWED_HOSTS=installer.yourdomain.com
CORS_ALLOWED_ORIGINS=https://installer.yourdomain.com

VAULT_MASTER_KEY=<64-hex>
DATABASE_URL=postgres://stripe_installer:stripe_installer@postgres:5432/stripe_installer
REDIS_URL=redis://redis:6379/0

CELERY_EAGER=false
CHANNEL_LAYER_INMEMORY=false

SAAS_BILLING_RETURN_URL=https://installer.yourdomain.com/billing
```

### Option A — Docker (recommended)

```powershell
npm run build:frontend
npm run docker:prod
```

Open `http://127.0.0.1:8000` locally, or put TLS proxy in front for your domain.

Services started: **postgres**, **redis**, **web**, **celery**, **celery-beat**.

### Option B — VPS manual

```powershell
docker compose up -d redis postgres
cd frontend && npm ci && npm run build
cd backend
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py collectstatic --noinput
# Terminal 1: celery -A config worker -l info
# Terminal 2: celery -A config beat -l info
# Terminal 3: daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

### TLS reverse proxy (Caddy example)

```
installer.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
```

WebSocket path for pipeline logs: `/ws/runs/{run_id}/?token={jwt}`

### Validate before DNS cutover

```powershell
npm run check:prod
# Or full deploy: npm run deploy:prod
curl http://127.0.0.1:8000/health/
```

### Day 3 checklist

- [ ] `check:prod` passes (or only expected warnings)
- [ ] `/health/` → `database`, `vault`, `redis` ok
- [ ] Register new user on production URL
- [ ] Create test project + vault init
- [ ] `VAULT_MASTER_KEY` backed up offline
- [ ] `frontend/dist` served (single origin on :8000 in Docker)

---

## Day 4 — Agency

**Goal:** Org for your agency, team members, shared client project, GitHub App.

### Create organization

1. **Agency** (`/agency`) → New organization (e.g. "Acme Agency")
2. Note your role: **owner**

### Invite team

1. Agency → select org → **Invite member** (email + role)
2. **Existing users** are added immediately
3. **New users** receive a register link (`/register?invite=…`) — copy from pending invites or email (SMTP in `.env`)
4. Roles: **owner** / **admin** / **member** / **viewer**

> Admin or owner required to invite. Free tier limits apply when `SAAS_STRIPE_*` is configured (Day 5).

**Email (optional):** set `EMAIL_BACKEND` to SMTP and `DEFAULT_FROM_EMAIL` in production `.env`. Dev uses console backend (invite links print in backend logs).

### Assign client project to org

1. Open client project → **Settings**
2. **Organization** → select your agency org → Save
3. Members with org access see the project on Agency dashboard

### GitHub App (PR readiness checks)

**In GitHub** (Settings → Developer settings → GitHub Apps → New):

| Setting | Value |
|---------|--------|
| Webhook URL | `https://installer.yourdomain.com/api/v1/webhooks/github/` |
| Webhook secret | Random string → `GITHUB_WEBHOOK_SECRET` in `.env` |
| Setup URL | `https://installer.yourdomain.com/agency/github/callback` |
| Permissions | Pull requests: Read; Checks: Write; Contents: Read |
| Events | Pull request, Installation |

**In `backend/.env`:**

```env
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n..."
GITHUB_APP_SLUG=your-app-slug
GITHUB_APP_SETUP_URL=https://installer.yourdomain.com/agency/github/callback
GITHUB_WEBHOOK_SECRET=<same as GitHub App>
```

**In app:** Agency → select org → **Install GitHub App** → authorize repos.

Client projects need `git_url` matching installed repos for PR checks to run.

### Day 4 checklist

- [ ] Org created; you are owner
- [ ] At least one member invited and can log in
- [ ] Client project assigned to org; member can open it
- [ ] GitHub App installed and linked (installation ID on org)
- [ ] Test PR on client repo triggers readiness (optional)

---

## Day 5 — Billing (SaaS)

**Goal:** Charge agencies for Stripe Installer via Stripe Checkout; org subscriptions unlock limits.

### Stripe Dashboard setup

1. Create products/prices (Starter, Pro, Enterprise) in **your** Stripe account (platform billing).
2. Copy price IDs → `SAAS_STRIPE_PRICE_*` in `.env`.
3. Developers → Webhooks → Add endpoint:

| Field | Value |
|-------|--------|
| URL | `https://installer.yourdomain.com/api/v1/billing/webhook/` |
| Events | `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted` |

4. Copy signing secret → `SAAS_STRIPE_WEBHOOK_SECRET`

### Billing `.env`

```env
SAAS_STRIPE_SECRET_KEY=sk_test_...   # sk_live_ when ready
SAAS_STRIPE_WEBHOOK_SECRET=whsec_...
SAAS_STRIPE_PRICE_STARTER=price_...
SAAS_STRIPE_PRICE_PRO=price_...
SAAS_STRIPE_PRICE_ENTERPRISE=price_...
SAAS_BILLING_RETURN_URL=https://installer.yourdomain.com/billing
ORG_FREE_MEMBER_LIMIT=3
ORG_FREE_PROJECT_LIMIT=5
```

Restart web after changing `.env`.

### Test org checkout

1. Log in as org **owner** or **admin**
2. **Billing** → Organization billing → select org → choose plan → Checkout
3. Use Stripe test card `4242 4242 4242 4242`
4. Return to Billing → subscription should show **active**
5. Agency dashboard → upgrade banner should clear for that org

### Test free-tier enforcement

With `SAAS_STRIPE_*` set and **no** org subscription:

- Inviting beyond `ORG_FREE_MEMBER_LIMIT` → 402 error
- Assigning beyond `ORG_FREE_PROJECT_LIMIT` org projects → validation error

### Local webhook testing

```powershell
stripe listen --forward-to http://127.0.0.1:8000/api/v1/billing/webhook/
# Use the whsec_ from stripe listen as SAAS_STRIPE_WEBHOOK_SECRET locally
```

### Day 5 checklist

- [ ] Plans appear on Billing page (not "not configured")
- [ ] Org checkout completes in test mode
- [ ] Webhook delivers; org subscription shows active
- [ ] Portal link works (manage subscription)
- [ ] Free limits enforced when unsubscribed

---

## After go-live

| Task | Command / doc |
|------|----------------|
| Vault key backup | Store `VAULT_MASTER_KEY` in password manager |
| Rotate vault key | `python manage.py rotate_vault_key` |
| MCP for Cursor | [MCP.md](./MCP.md) |
| Smoke test | `npm run smoke` |
| Production audit | `npm run check:prod` |

---

## Quick reference — URLs

| Purpose | Path |
|---------|------|
| Health | `/health/` |
| API | `/api/v1/` |
| SaaS billing webhook | `/api/v1/billing/webhook/` |
| GitHub App webhook | `/api/v1/webhooks/github/` |
| Agency GitHub callback | `/agency/github/callback` |
| Pipeline WebSocket | `/ws/runs/{id}/?token={jwt}` |
