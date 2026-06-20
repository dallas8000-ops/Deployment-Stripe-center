# Merge status — Deployment & Stripe Automation Center

Last updated: merge session complete for **code + docs + portfolio linking**. Production Railway/Stripe cutover is **your action**.

## Completed

### Unified app (`Deployment-Stripe-center`)

- [x] API Transfer module in `backend/apps/api_transfer/` (deploy, transfer runs, worker, audit, metrics)
- [x] Project Transfer UI (`TransferPanel.tsx`, `/deploy` page)
- [x] Audit log API (`GET /transfer/audit/`)
- [x] Transfer metrics in API + UI
- [x] Cutover guide: [CUTOVER.md](CUTOVER.md)
- [x] Portfolio linking documented in [api_transfer/README.md](../backend/apps/api_transfer/README.md)
- [x] Portfolio registry template (`automation-center` + legacy entry marked for removal)

### Portfolio site (`FrontlineDigital/DevCollective`)

- [x] Single flagship card: **Deployment & Stripe Automation Center**
- [x] Removed separate **API Transfer** card
- [x] `portfolioLiveUrls.automationCenter` → `stripe-installer-production.up.railway.app/login`
- [x] `api-transfer-production` added to deprecated hosts (stale URL remap)
- [x] Playwright test updated for new card title
- [x] `siteContent` schema v10 (refreshes stale localStorage project lists)

## Your steps to finish production cutover

These require Railway Dashboard + Stripe Dashboard access:

1. [ ] Merge API Transfer **env vars** onto `stripe-installer-production` Railway service — **include one permanent `VAULT_MASTER_KEY`** (see [RAILWAY.md](RAILWAY.md#vault-master-key-read-this-first))
2. [ ] Verify unified app: `curl https://stripe-installer-production.up.railway.app/health/`
3. [ ] Test login, one deploy, Render→Railway dry run on a project
4. [ ] Stripe: disable webhook on `api-transfer-production.../api/billing/webhook`
5. [ ] Keep one webhook: `.../api/v1/billing/webhook/` on unified service
6. [ ] **Deploy FrontlineDigital** frontend (Porkbun portfolio picks up new Live demo link)
7. [ ] Delete `api-transfer-production` Railway service (after 48h no traffic)
8. [ ] Update `~/.stripe-installer/portfolio-registry.json` — remove `api-transfer-legacy`
9. [ ] Archive local `API Transfer` folder when comfortable

**Porkbun / gilliomfrontlinedigital.com:** no change needed — portfolio stays on `frontlinedigital-1-production`; demo buttons use Railway URLs directly.

## Not in scope (optional future work)

- Discover / plan / apply / rollback engine
- Terraform plan/apply
- Console bootstrap + client prewire
- Full test port from standalone API Transfer repo

These do **not** block production cutover if you use deploy + Render→Railway transfer features already merged.

## Verify portfolio after deploy

1. Open [gilliomfrontlinedigital.com](https://gilliomfrontlinedigital.com/)
2. Find **Deployment & Stripe Automation Center** — one card, no separate API Transfer
3. **Live demo** → `stripe-installer-production.up.railway.app/login`
4. Log in and confirm **API Transfer** section on a project workspace

When steps 1–9 above are done, the merge is **fully complete** in production.
