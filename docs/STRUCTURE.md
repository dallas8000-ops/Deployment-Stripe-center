# Deployment & Stripe Automation Center

One deployable product: **API Transfer** + **Stripe Installer** on shared projects, vault, and auth.

```
deployment-stripe-center/          # repo root (this folder)
├── backend/
│   ├── config/                    # Django settings, URLs, ASGI
│   ├── manage.py
│   └── apps/
│       ├── projects/              # Shared Project model, scanner, GitHub
│       ├── vault/                 # Encrypted secrets (per project)
│       ├── api_transfer/          # Deploy / migrate (Railway, Render, …)
│       ├── stripe_installer/      # Stripe setup, codegen, pipeline
│       ├── diagnostics/           # Diagnose, readiness, drift, webhook health
│       ├── ai_assistant/          # Copilot, NL config, handoff
│       ├── runs/                  # Pipeline runs, WebSocket logs
│       ├── deploy/                # Deploy prep, Railway push, postgres
│       ├── billing/               # SaaS subscriptions
│       ├── accounts/              # Users (email login)
│       ├── organizations/         # Agency / workspaces
│       ├── core/                  # Access control, health
│       └── licenses/              # Software protection
├── frontend/
│   └── src/
│       ├── pages/                 # Dashboard, project workspace, deploy
│       ├── components/
│       └── api/                   # API client (no secrets)
├── private_env/                   # Local-only tokens (*.env — gitignored)
├── docs/
├── scripts/
└── docker-compose.yml
```

## Secret layers

| Layer | Purpose |
|-------|---------|
| `private_env/*.env` | Your dev platform tokens (never git) |
| `~/.stripe-installer/` | Master key + per-project vault backup |
| Database vault | Per-project secrets for all modules |
| Frontend | Status only — never secret values |

## Module access pattern

```python
from apps.vault.services import get_project_secret

railway = get_project_secret(project, "RAILWAY_API_TOKEN")
stripe = get_project_secret(project, "STRIPE_SECRET_KEY")
```

## Related docs

- [AUTOMATION-CENTER.md](AUTOMATION-CENTER.md) — merge plan with API Transfer
- [GO-LIVE.md](GO-LIVE.md) — production checklist
