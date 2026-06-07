import type { StripeManifest } from "../types.js";
import { formatAmount, tierCardsFromManifest, tierKey } from "./tier-format.js";

/** Server-rendered Django templates — no React, no localStorage, no client-side fetch. */
export function generateDjangoTemplateFiles(manifest?: StripeManifest | null): Record<string, string> {
  const tiers = tierCardsFromManifest(manifest);
  const tierRows = tiers
    .map(
      (t) => `    <article class="tier-card">
      <h2>${t.tier}</h2>
      <p class="price">${t.label}</p>
      ${t.trialDays ? `<p class="trial">${t.trialDays}-day free trial</p>` : ""}
      ${t.features.length ? `<ul>${t.features.map((f) => `<li>${f}</li>`).join("")}</ul>` : ""}
      <form method="post" action="{% url 'stripe-checkout' %}">
        {% csrf_token %}
        <input type="hidden" name="priceId" value="${t.priceId}" />
        <button type="submit">Subscribe</button>
      </form>
    </article>`
    )
    .join("\n");

  return {
    "stripe/templates/stripe/pricing.html": `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pricing — {{ block.super }}</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; }
    .grid { display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); margin-top: 2rem; }
    .tier-card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; }
    .price { font-size: 1.75rem; font-weight: bold; }
    .trial { color: #059669; font-size: 0.875rem; }
    button { margin-top: 1rem; padding: 0.5rem 1rem; background: #111; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
  </style>
</head>
<body>
  <h1>Choose your plan</h1>
  <p>Simple, transparent pricing — server-rendered for SEO.</p>
  <div class="grid">
${tierRows || "    <p>Run <code>stripe-installer run --provision</code> to create tiers.</p>"}
  </div>
</body>
</html>
`,
    "stripe/templates/stripe/success.html": `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Payment successful</title>
</head>
<body style="font-family:system-ui;text-align:center;margin:4rem auto">
  <h1 style="color:#059669">Payment successful</h1>
  <p>Thank you for your purchase.</p>
  {% if session_id %}<p style="font-size:0.75rem;color:#9ca3af">Reference: {{ session_id }}</p>{% endif %}
  <p><a href="{% url 'stripe-account' %}">Go to account</a></p>
</body>
</html>
`,
    "stripe/templates/stripe/account.html": `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Account</title>
</head>
<body style="font-family:system-ui;max-width:480px;margin:2rem auto;padding:1rem">
  <h1>Account</h1>
  <p>Manage your subscription and billing.</p>
  {% if customer_id %}
    <form method="post" action="{% url 'stripe-portal' %}">
      {% csrf_token %}
      <input type="hidden" name="customerId" value="{{ customer_id }}" />
      <button type="submit">Manage subscription</button>
    </form>
  {% else %}
    <p>No Stripe customer linked yet. Complete checkout first.</p>
    <p><a href="{% url 'stripe-pricing' %}">View plans</a></p>
  {% endif %}
</body>
</html>
`,
  };
}

export function djangoPageViews(manifest?: StripeManifest | null): string {
  const tiers = (manifest?.prices ?? [])
    .map((p) => {
      const key = tierKey(p.tier);
      const label = formatAmount(p.amount, p.currency) + (p.interval ? `/${p.interval}` : "");
      return `    {"key": "${key}", "tier": "${p.tier}", "price_id": "${p.id}", "label": "${label}"},`;
    })
    .join("\n");

  return `
STRIPE_TIERS = [
${tiers || "    # Run stripe-installer run --provision first"}
]


def pricing(request):
    return render(request, "stripe/pricing.html", {"tiers": STRIPE_TIERS})


def success(request):
    session_id = request.GET.get("session_id")
    if session_id:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            customer_id = session.customer if isinstance(session.customer, str) else getattr(session.customer, "id", None)
            if customer_id:
                request.session["stripe_customer_id"] = customer_id
        except stripe.error.StripeError:
            pass
    return render(request, "stripe/success.html", {"session_id": session_id})


def account(request):
    customer_id = request.session.get("stripe_customer_id")
    if not customer_id and getattr(request, "user", None) and request.user.is_authenticated:
        customer_id = _customer_id_for_user(request.user)
    return render(request, "stripe/account.html", {"customer_id": customer_id})


def _customer_id_for_user(user):
    from .db import get_stripe_customer_for_user
    return get_stripe_customer_for_user(user.pk)
`;
}

export function djangoSessionView(): string {
  return `
@csrf_exempt
@require_POST
def session_info(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    session_id = data.get("sessionId")
    if not session_id:
        return JsonResponse({"error": "sessionId required"}, status=400)
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:
        return JsonResponse({"error": str(e)}, status=400)
    customer_id = session.customer if isinstance(session.customer, str) else getattr(session.customer, "id", None)
    return JsonResponse({
        "customerId": customer_id,
        "email": session.customer_email,
        "status": session.status,
    })
`;
}

export function djangoUrlsWithPages(includeConnect = true): string {
  const connectPaths = includeConnect
    ? `
    path("me", views.stripe_me, name="stripe-me"),
    path("connect/onboard", views.connect_onboard, name="stripe-connect-onboard"),
    path("connect/return", views.connect_return, name="stripe-connect-return"),
    path("connect/transfer", views.connect_transfer, name="stripe-connect-transfer"),
    path("connect/dashboard", views.connect_dashboard, name="stripe-connect-dashboard"),`
    : `
    path("me", views.stripe_me, name="stripe-me"),`;

  return `from django.urls import path

from . import views

urlpatterns = [
    path("webhook", views.webhook, name="stripe-webhook"),
    path("checkout", views.checkout, name="stripe-checkout"),
    path("portal", views.portal, name="stripe-portal"),
    path("session", views.session_info, name="stripe-session"),
    path("pricing", views.pricing, name="stripe-pricing"),
    path("success", views.success, name="stripe-success"),
    path("account", views.account, name="stripe-account"),${connectPaths}
]
`;
}
