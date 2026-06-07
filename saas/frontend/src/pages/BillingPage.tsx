import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { billingApi, type BillingPlan, type SubscriptionInfo } from "../api/client";
import ScoreRing from "../components/ScoreRing";

export default function BillingPage() {
  const [search] = useSearchParams();
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [configured, setConfigured] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const success = search.get("success") === "1";

  async function load() {
    try {
      const [planData, sub] = await Promise.all([billingApi.plans(), billingApi.subscription()]);
      setPlans(planData.plans);
      setConfigured(planData.configured);
      setSubscription(sub);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load billing");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function checkout(priceId: string) {
    setBusy(priceId);
    setError("");
    try {
      const { url } = await billingApi.checkout(priceId);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
      setBusy("");
    }
  }

  async function openPortal() {
    setBusy("portal");
    setError("");
    try {
      const { url } = await billingApi.portal();
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portal failed");
      setBusy("");
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Billing</h1>
          <p className="muted">
            Stripe Installer SaaS — powered by the same checkout + portal flow we generate for you.
          </p>
        </div>
        {subscription?.isActive && (
          <ScoreRing score={100} label="Pro" sublabel={subscription.tier || "active"} size={72} />
        )}
      </div>

      {success && (
        <div className="alert alert-success">Subscription updated — welcome aboard!</div>
      )}
      {error && <div className="alert alert-error">{error}</div>}

      {!configured && (
        <div className="alert alert-warn">
          Platform billing is not configured. Set <code>SAAS_STRIPE_SECRET_KEY</code> and price IDs in backend
          .env.
        </div>
      )}

      {subscription && (
        <section className="card">
          <h2>Your subscription</h2>
          <div className="billing-status-grid">
            <div>
              <span className="muted">Status</span>
              <strong>{subscription.status}</strong>
            </div>
            <div>
              <span className="muted">Plan</span>
              <strong>{subscription.tier || "—"}</strong>
            </div>
            <div>
              <span className="muted">Renews</span>
              <strong>
                {subscription.currentPeriodEnd
                  ? new Date(subscription.currentPeriodEnd).toLocaleDateString()
                  : "—"}
              </strong>
            </div>
          </div>
          {subscription.customerId && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={openPortal}
              disabled={busy === "portal"}
              style={{ marginTop: 16 }}
            >
              {busy === "portal" ? "Opening…" : "Manage subscription"}
            </button>
          )}
        </section>
      )}

      <section className="card">
        <h2>Plans</h2>
        {!subscription?.isActive ? (
          <div className="pricing-grid">
            {plans.map((plan) => (
              <article key={plan.priceId} className="pricing-card">
                <h3>{plan.label}</h3>
                <p className="price-tag">${(plan.amount / 100).toFixed(0)}/mo</p>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!configured || busy === plan.priceId}
                  onClick={() => checkout(plan.priceId)}
                >
                  {busy === plan.priceId ? "Redirecting…" : "Subscribe"}
                </button>
              </article>
            ))}
            {plans.length === 0 && configured && (
              <p className="muted">No plans configured — set SAAS_STRIPE_PRICE_* env vars.</p>
            )}
          </div>
        ) : (
          <p className="muted">
            You have an active subscription. Use the portal to change plans or cancel.
          </p>
        )}
      </section>

      <p className="muted">
        <Link to="/">← Back to projects</Link>
      </p>
    </div>
  );
}
