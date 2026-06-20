# Merge status — Deployment & Stripe Automation Center

Last updated: cutover verification pass.

## Completed

### Unified app (`Deployment-Stripe-center`)

- [x] API Transfer module in `backend/apps/api_transfer/` (deploy, transfer runs, worker, audit, metrics)
- [x] Project Transfer UI (`TransferPanel.tsx`, `/deploy` page)
- [x] Audit log API (`GET /transfer/audit/`)
- [x] Transfer metrics in API + UI
- [x] Cutover guide: [CUTOVER.md](CUTOVER.md)
- [x] Portfolio linking documented in [api_transfer/README.md](../backend/apps/api_transfer/README.md)
- [x] Portfolio registry template (`automation-center` only — legacy entry removed)
- [x] `VAULT_MASTER_KEY` env priority on Railway ([master_key.py](../backend/apps/vault/master_key.py))
- [x] `python manage.py verify_cutover` — live health + registry checks
- [x] `scripts/complete-cutover.ps1` — Railway/Stripe checklist helper

### Portfolio site (`FrontlineDigital/DevCollective`)

- [x] Single flagship card: **Deployment & Stripe Automation Center**
- [x] Removed separate **API Transfer** card
- [x] `portfolioLiveUrls.automationCenter` → `stripe-installer.gilliomfrontlinedigital.com/login`
- [x] Custom domain on unified service: `stripe-installer.gilliomfrontlinedigital.com`
- [x] `api-transfer-production` added to deprecated hosts (stale URL remap)
- [x] Playwright test updated for new card title
- [x] `siteContent` schema v10 (refreshes stale localStorage project lists)

### Production verification (live)

- [x] `GET https://stripe-installer-production.up.railway.app/health/` → `"status":"ok"`, `"vault":"ok"`
- [x] `VAULT_MASTER_KEY` pinned on Railway (user confirmed)
- [x] `~/.stripe-installer/portfolio-registry.json` created (automation-center only)

## Remaining (manual — Railway / Stripe dashboard)

These require Stripe Dashboard clicks or optional provider token setup:

1. [ ] **Stripe-Installer service vars** — already sufficient for app + billing if health shows `vault: ok`  
   Your service has `STRIPE_*`, `DATABASE_URL`, `DJANGO_*`, `CORS/CSRF` — no copy needed from api-transfer  
   Legacy names on unified service (`VAULT_MASTER_KEY_BASE64`, `VAULT_DJANGO_SECRET_KEY`) are **ignored** — use `VAULT_MASTER_KEY` (64-char hex) if not already set  
   **Deploy tokens** (`RAILWAY_API_TOKEN`, `GITHUB_TOKEN`, etc.) were **never** api-transfer Railway vars — store them in **each project's vault** in the app, or add optionally at service level later
2. [ ] **Disable Stripe webhook** on `api-transfer-production.../api/billing/webhook`  
   Keep: `stripe-installer-production.../api/v1/billing/webhook/`  
   Dashboard: Developers -> Webhooks -> `api-transfer-production` -> Disable  
   CLI (needs secret key with webhook write):  
   `stripe webhook_endpoints update we_1ThOh0RxznXvj6jhjt7jZ3nm --disabled=true --live -c`
3. [ ] **Redeploy unified service** after any variable changes (Railway → Deploy latest `main`)
4. [ ] **Smoke test** in app: login → project → Transfer panel → dry-run deploy
5. [ ] **Delete `api-transfer-production`** Railway service (after 48h no traffic)
6. [ ] **Archive** local `API Transfer` / `API-Transfer` folder when comfortable

**Porkbun / gilliomfrontlinedigital.com:** no DNS change — portfolio on `frontlinedigital-1-production`; demo buttons use Railway URLs.

## Verify anytime

```bash
curl https://stripe-installer-production.up.railway.app/health/
cd backend && python manage.py verify_cutover
powershell -File scripts/complete-cutover.ps1
```

When steps 1–5 above are done, the merge is **fully complete** in production.
