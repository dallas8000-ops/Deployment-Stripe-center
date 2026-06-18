# Portfolio Stripe audit (local only)

Audits **your whole Stripe account** against apps you allow on this PC. Reports and registry live under **`~/.stripe-installer/`** — never in git, never pushed.

## What it does

1. Reads **`~/.stripe-installer/portfolio-registry.json`** (allowed apps, production URLs, webhook paths).
2. Lists every webhook endpoint in Stripe (same account as your vault key).
3. **HTTP-probes** each webhook URL and each app’s health URL.
4. Flags mismatches (100% Dashboard errors usually mean app down, wrong path, or bad `whsec_`).
5. Writes **`~/.stripe-installer/reports/portfolio-audit-*.md`** and **`LATEST.md`** (no secrets).

## What it does **not** do

- **Create `sk_` / `pk_` keys via API** — Stripe does not allow that. The report links to Dashboard → API keys.
- **Fix Railway/Render hosting** — if the app returns 502, fix deploy first; then re-run audit.
- **Sync secrets to Railway** — after `--fix`, copy `STRIPE_WEBHOOK_SECRET` to the host manually.

## Setup (once)

1. Edit registry (created on first run):

   `C:\Users\<you>\.stripe-installer\portfolio-registry.json`

2. For each app add `id`, `productionUrl`, `webhookPath`, `projectSlug` (Stripe Installer project slug).

3. Optional: `transferAllowedTo` — list of app IDs allowed to receive vault exports (enforced by registry; export UI coming later).

## Run

```powershell
cd backend
python manage.py stripe_installer portfolio-audit --project stripe-installer
```

Use any project whose vault has the **Stripe account** secret you want to audit (one account, many endpoints).

```powershell
# Re-register webhooks for registry apps (after app is live)
python manage.py stripe_installer portfolio-audit --project stripe-installer --fix
```

Open the report:

`~/.stripe-installer/reports/LATEST.md`

## UI (per project)

In Stripe Installer → **Project → Health & Readiness → Stripe webhook advisor**:

1. **Open API keys / Open webhooks** — Dashboard links (test vs live from your vault key).
2. **Run webhook advisor** — classifies root cause and shows ordered playbook steps.
3. **Confirm / re-scan** — after you fix hosting or secrets, re-run until `HEALTHY`.


| Dashboard signal | Likely cause |
|------------------|--------------|
| **100% error rate** | App not listening (502), wrong URL path, or `STRIPE_WEBHOOK_SECRET` mismatch |
| **0% errors, 0 events** | Endpoint registered but no traffic yet |
| **0% errors, events flowing** | Healthy |

Stripe Installer cannot fix a dead Railway deploy — it can tell you **which URL failed the probe** and **open the Dashboard link** for that endpoint.

## Security

| Location | In git? | Contains secrets? |
|----------|---------|-------------------|
| `portfolio-registry.json` | No | URLs only |
| `reports/*.md` | No | No |
| Project vault (Postgres) | No | Yes — never exported in reports |

Override data dir: `STRIPE_INSTALLER_DATA_DIR=C:\private\stripe-installer-data`
