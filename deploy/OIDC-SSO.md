# Enterprise OIDC SSO

Phase 2 SSO uses the standard OIDC authorization code flow (Okta, Azure AD, Google Workspace, etc.).

## Enable

Set on Railway (all services) or `backend/.env`:

```
OIDC_SSO_ENABLED=true
OIDC_ISSUER_URL=https://login.microsoftonline.com/{tenant}/v2.0
OIDC_CLIENT_ID=...
OIDC_CLIENT_SECRET=...
OIDC_REDIRECT_URI=https://your-domain/api/v1/auth/sso/callback/
OIDC_ALLOWED_EMAIL_DOMAINS=yourcompany.com
```

`OIDC_REDIRECT_URI` must match the IdP app registration exactly. Local dev via Vite proxy:

```
OIDC_REDIRECT_URI=http://localhost:5173/api/v1/auth/sso/callback/
```

## Flow

1. User clicks **Sign in with SSO** on `/login`.
2. Browser → `GET /api/v1/auth/sso/login/` → IdP authorize URL.
3. IdP redirects to `/api/v1/auth/sso/callback/?code=...&state=...`.
4. Backend exchanges code, provisions user by email, redirects to `/auth/sso/callback#access=...&refresh=...`.
5. SPA stores JWT tokens and continues.

## User provisioning

- Users are matched or created by **email** from OIDC `userinfo`.
- Optional `OIDC_ALLOWED_EMAIL_DOMAINS` restricts which email domains may sign in.
- SSO users can still enable **TOTP MFA** from **Account → Security** after first login.

## Okta example

- Issuer: `https://{yourOktaDomain}/oauth2/default`
- Scopes: `openid email profile`
- Redirect URI: `https://<your-domain>/api/v1/auth/sso/callback/`

## Azure AD example

- Issuer: `https://login.microsoftonline.com/{tenant-id}/v2.0`
- Register redirect URI as above
- Grant `openid`, `email`, `profile` delegated permissions
