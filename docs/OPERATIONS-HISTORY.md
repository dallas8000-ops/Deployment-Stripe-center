# Cutover and Operations History

Legacy cutover notes moved from the README, kept verbatim for reference. Status rows reflect the last time `verify_cutover` was run and may already be resolved; re-run it for current state.

## Last cutover verification

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

## Cutover steps (retire api-transfer-production)

Remaining manual steps — see [docs/MERGE-STATUS.md](MERGE-STATUS.md):

1. Finish TLS on custom domain (Railway Networking).
2. Disable legacy Stripe webhook on `api-transfer-production.../api/billing/webhook`.
3. Smoke test: login → project → Transfer panel.
4. Redeploy portfolio (`frontlinedigital-1-production`) for updated demo URL.
5. After 48h quiet → delete `api-transfer-production` Railway service.

Helper: `powershell -File scripts/complete-cutover.ps1`
