/** Stripe Connect — onboarding + transfers for generated Django apps. */

export function generateDjangoConnectViews(): string {
  return `
def connect_onboard(request):
    """Start Express Connect onboarding for the logged-in user."""
    if not request.user.is_authenticated:
        return redirect("/accounts/login/?next=/stripe/connect/onboard/")
    app_url = os.environ.get("APP_URL", "http://localhost:8000")
    from .db import get_connect_account_for_user

    account_id = get_connect_account_for_user(request.user.pk)
    if not account_id:
        account = stripe.Account.create(
            type="express",
            metadata={"auth_user_id": str(request.user.pk)},
            capabilities={"transfers": {"requested": True}},
        )
        account_id = account.id
    link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=f"{app_url}/stripe/connect/onboard/",
        return_url=f"{app_url}/stripe/connect/return/",
        type="account_onboarding",
    )
    return redirect(link.url)


def connect_return(request):
    """Return URL after Connect onboarding."""
    return render(
        request,
        "stripe/connect_return.html",
        {"message": "Connect onboarding complete. You can receive transfers when enabled."},
    )


@require_POST
def connect_transfer(request):
    """Platform → connected account transfer (server-side only).

    POST body: amount (cents), currency, destination (acct_...) optional if user has linked account.
    Restrict to staff in production: @user_passes_test(lambda u: u.is_staff)
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    amount = _post_value(request, "amount")
    currency = _post_value(request, "currency") or "usd"
    destination = _post_value(request, "destination")

    if not amount:
        return JsonResponse({"error": "amount required (integer cents)"}, status=400)
    try:
        amount_int = int(amount)
    except (TypeError, ValueError):
        return JsonResponse({"error": "amount must be integer cents"}, status=400)

    if not destination:
        from .db import get_connect_account_for_user
        destination = get_connect_account_for_user(request.user.pk)
    if not destination:
        return JsonResponse({"error": "destination Connect account required"}, status=400)

    transfer = stripe.Transfer.create(
        amount=amount_int,
        currency=currency,
        destination=destination,
        metadata={"initiated_by": str(request.user.pk)},
    )
    from .db import record_transfer
    record_transfer({
        "id": transfer.id,
        "destination": transfer.destination,
        "amount": transfer.amount,
        "currency": transfer.currency,
        "status": "created",
    })
    return JsonResponse({"transferId": transfer.id, "amount": transfer.amount, "destination": transfer.destination})


def connect_dashboard(request):
    """Express Dashboard login link for the user's connected account."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    from .db import get_connect_account_for_user

    account_id = get_connect_account_for_user(request.user.pk)
    if not account_id:
        return JsonResponse({"error": "No Connect account — complete onboarding first"}, status=404)
    link = stripe.Account.create_login_link(account_id)
    return redirect(link.url)
`;
}

export function generateDjangoConnectTemplates(): Record<string, string> {
  return {
    "stripe/templates/stripe/connect_return.html": `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8" /><title>Connect setup</title></head>
<body style="font-family:system-ui;max-width:480px;margin:4rem auto;text-align:center">
  <h1>Connect account</h1>
  <p>{{ message }}</p>
  <p><a href="{% url 'stripe-account' %}">Back to account</a></p>
</body>
</html>
`,
  };
}

export function djangoConnectUrls(): string {
  return `
    path("me", views.stripe_me, name="stripe-me"),
    path("connect/onboard", views.connect_onboard, name="stripe-connect-onboard"),
    path("connect/return", views.connect_return, name="stripe-connect-return"),
    path("connect/transfer", views.connect_transfer, name="stripe-connect-transfer"),
    path("connect/dashboard", views.connect_dashboard, name="stripe-connect-dashboard"),
`;
}

export function djangoConnectSetupGuide(): string {
  return `# Stripe Connect — transfers (Django)

Platform collects payments; **Transfers** move funds to connected Express accounts.

## 1. Enable Connect
Stripe Dashboard → Connect → enable Express accounts.

## 2. Environment
\`\`\`
STRIPE_SECRET_KEY=sk_...          # platform secret key
STRIPE_WEBHOOK_SECRET=whsec_...
APP_URL=https://yourdomain.com
\`\`\`

## 3. Webhook events (register on platform account)
- \`account.updated\`
- \`transfer.created\`
- \`transfer.updated\`
- \`transfer.reversed\`

## 4. Routes
| URL | Purpose |
|-----|---------|
| \`/stripe/connect/onboard/\` | Start Express onboarding |
| \`/stripe/connect/return/\` | Post-onboarding landing |
| \`/stripe/connect/dashboard/\` | Express Dashboard login |
| \`/stripe/connect/transfer/\` | POST transfer (staff only by default) |

## 5. Deterministic linking
Connect accounts store \`metadata.auth_user_id\` = Django \`User.pk\`.
Webhooks sync to \`stripe_connect_accounts.auth_user_id\`.

## 6. Create a transfer (server-side)
\`\`\`bash
curl -X POST https://yourdomain.com/stripe/connect/transfer/ \\
  -H "Cookie: sessionid=..." \\
  -d "amount=5000&currency=usd&destination=acct_..."
\`\`\`
Amount is in **cents**. Use \`destination\` or rely on DB lookup for the user's linked account.

See https://docs.stripe.com/connect/transfers
`;
}
