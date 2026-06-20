# Stripe + Auth - Django

## Deterministic customer linking
1. `checkout` passes `client_reference_id=str(request.user.pk)` when authenticated.
2. Webhook `checkout.session.completed` writes to `stripe_customers.auth_user_id`.
3. `GET /stripe/me/` resolves customer via DB lookup.

## API
| Method | URL | Auth | Returns |
|--------|-----|------|---------|
| GET | `/stripe/me/` | Login required | `{ customerId, source, subscription? }` |

## Session fallback
`success` view stores `stripe_customer_id` in session for guests; DB is source of truth for logged-in users.
