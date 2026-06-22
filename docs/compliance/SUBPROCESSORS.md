# Subprocessors

Third parties that may process **customer data** when you operate Automation Center in production. Update this list when you add integrations.

Last reviewed: 2026-06-22

| Subprocessor | Purpose | Data categories | Location | DPA |
|--------------|---------|-----------------|----------|-----|
| **Railway** | App hosting, Postgres, Redis | Account email, project metadata, encrypted vault ciphertext, logs | US | [Railway DPA](https://railway.com/legal/dpa) |
| **Stripe** | SaaS billing, Connect (client projects) | Billing email, payment metadata | US / global | [Stripe DPA](https://stripe.com/legal/dpa) |
| **GitHub** | Repo access, deploy hooks | Repo names, commit metadata | US | [GitHub DPA](https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement) |
| **Sentry** (optional) | Error monitoring | Stack traces, request IDs (no vault secrets by design) | US / EU | [Sentry DPA](https://sentry.io/legal/dpa/) |
| **Neon / Supabase** (optional) | Client Postgres provisioning | Connection strings (stored encrypted in vault) | Varies | Provider DPA |

## Not subprocessors (customer-controlled)

- Client cloud accounts (Fly, Render, Cloudflare) — credentials stored in **per-project vault**
- OIDC IdP (Okta, Azure AD) — customer IdP when `OIDC_SSO_ENABLED=true`

## Notification

Enterprise customers: notify within **30 days** of adding a new subprocessor that processes their org data. Maintain changelog entries in this file.
