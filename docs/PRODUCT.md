# Product focus

## One-liner

**Encrypted vault + Stripe automation for agencies shipping client apps to production** — one login to scan repos, wire billing, and push deploys without secrets leaving the server.

## Wedge

| Pain | Automation Center |
|------|-------------------|
| Stripe products/prices/webhooks scattered across client repos | Guided installer + drift detection + auto-heal |
| API keys in `.env` and chat logs | Per-project encrypted vault; redacted audits |
| Two tools (Stripe Installer + API Transfer) | Single Django + React app |
| Railway/Render/Fly env drift | Discover → plan → apply transfer runs |

## ICP

- Agencies and indie studios with **multiple client codebases**
- Django/React (or similar) apps going to **Railway** first
- Operators who need **audit trail** for deploy and billing changes

## Not building (Tier-1 scope)

- Generic CI/CD replacement (use GitHub Actions + our deploy hooks)
- Full Terraform IDE (transfer runs cover common paths)
- Archived Node CLI (`legacy/`) — reference only until removed post-cutover

## Success metrics

- Time from repo link → Stripe test checkout < 1 hour
- Zero plaintext secrets in frontend network tab
- Transfer dry-run before every production apply
