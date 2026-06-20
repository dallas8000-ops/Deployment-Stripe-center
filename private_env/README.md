# Private environment files (local only)

**Never commit real values.** This folder is gitignored.

Copy the `.example` files here and fill in your keys:

```powershell
copy stripe.env.example stripe.env
copy railway.env.example railway.env
copy render.env.example render.env
copy github.env.example github.env
```

The backend loads `private_env/*.env` on startup for **your machine only** — platform tokens for API Transfer and Stripe Installer dev.

Per-project secrets (client apps) go in the **encrypted vault** in the database, not here.
