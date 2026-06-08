import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { billingApi, orgsApi, type BillingPlan, type OrgSubscriptionInfo, type Organization, type SubscriptionInfo } from "../api/client";
import ScoreRing from "../components/ScoreRing";

export default function BillingPage() {
  const [search] = useSearchParams();
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState("");
  const [orgSubscription, setOrgSubscription] = useState<OrgSubscriptionInfo | null>(null);
  const [configured, setConfigured] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const success = search.get("success") === "1";

  const orgParam = search.get("org") || "";

  async function load() {
    setError("");
    setLoading(true);
    try {
      const planData = await billingApi.plans();
      setPlans(planData.plans);
      setConfigured(planData.configured);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plans");
    }

    try {
      setSubscription(await billingApi.subscription());
    } catch (err) {
      setError((prev) => prev || (err instanceof Error ? err.message : "Failed to load subscription"));
    }

    try {
      const orgList = await orgsApi.list();
      setOrgs(orgList.filter((o) => o.my_role === "owner" || o.my_role === "admin"));
      const orgSlug = orgParam || selectedOrg || orgList[0]?.slug || "";
      if (orgSlug) {
        setSelectedOrg(orgSlug);
        try {
          setOrgSubscription(await billingApi.orgSubscription(orgSlug));
        } catch {
          setOrgSubscription(null);
        }
      }
    } catch {
      // Org billing is optional — old backends return 404 here
      setOrgs([]);
      setOrgSubscription(null);
    } finally {
      setLoading(false);
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

  async function orgCheckout(priceId: string) {
    if (!selectedOrg) return;
    setBusy(`org-${priceId}`);
    setError("");
    try {
      const { url } = await billingApi.orgCheckout(selectedOrg, priceId);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Org checkout failed");
      setBusy("");
    }
  }

  async function openOrgPortal() {
    if (!selectedOrg) return;
    setBusy("org-portal");
    setError("");
    try {
      const { url } = await billingApi.orgPortal(selectedOrg);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Org portal failed");
      setBusy("");
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Billing</h1>
          <p className="muted">
            Your <strong>Stripe Installer</strong> subscription — separate from Stripe keys in each project&apos;s
            vault.
          </p>
        </div>
        {subscription?.isActive && (
          <ScoreRing score={100} label="Pro" sublabel={subscription.tier || "active"} size={72} />
        )}
      </div>

      {loading && <p className="muted">Loading billing…</p>}

      {success && (
        <div className="alert alert-success">Subscription updated — welcome aboard!</div>
      )}
      {error && <div className="alert alert-error">{error}</div>}

      {!configured && (
        <section className="card billing-dev-card">
          <h2>Not enabled in local dev</h2>
          <p className="muted">
            Platform billing is <strong>optional</strong>. You can use the full app — projects, vault, pipeline,
            deploy — without it.
          </p>
          <p className="muted">
            To bill users for <em>Stripe Installer itself</em> (dogfooding our checkout flow), add these to{" "}
            <code>backend/.env</code> and restart the backend:
          </p>
          <pre className="verify-pre billing-env-pre">{`SAAS_STRIPE_SECRET_KEY=sk_test_...
SAAS_STRIPE_PRICE_STARTER=price_...
SAAS_STRIPE_PRICE_PRO=price_...
SAAS_STRIPE_PRICE_ENTERPRISE=price_...
SAAS_BILLING_RETURN_URL=http://127.0.0.1:5173`}</pre>
          <p className="muted vault-hint">
            For your <strong>client app&apos;s</strong> Stripe integration, use Projects → vault → pipeline — not
            this page.
          </p>
        </section>
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

      {orgs.length > 0 && (
        <section className="card">
          <h2>Organization billing</h2>
          <p className="muted">Bill an agency org separately from your personal account.</p>
          <label>
            Organization
            <select
              value={selectedOrg}
              onChange={async (e) => {
                const slug = e.target.value;
                setSelectedOrg(slug);
                try {
                  setOrgSubscription(await billingApi.orgSubscription(slug));
                } catch {
                  setOrgSubscription(null);
                }
              }}
            >
              {orgs.map((o) => (
                <option key={o.id} value={o.slug}>
                  {o.name} ({o.my_role})
                </option>
              ))}
            </select>
          </label>
          {orgSubscription && (
            <div className="billing-status-grid">
              <div>
                <span className="muted">Status</span>
                <strong>{orgSubscription.status}</strong>
              </div>
              <div>
                <span className="muted">Plan</span>
                <strong>{orgSubscription.tier || "—"}</strong>
              </div>
            </div>
          )}
          {orgSubscription?.customerId && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={openOrgPortal}
              disabled={busy === "org-portal"}
              style={{ marginTop: 16 }}
            >
              {busy === "org-portal" ? "Opening…" : "Manage org subscription"}
            </button>
          )}
          {configured && orgSubscription && !orgSubscription.isActive && (
            <div className="pricing-grid" style={{ marginTop: 16 }}>
              {plans.map((plan) => (
                <article key={`org-${plan.priceId}`} className="pricing-card">
                  <h3>{plan.label} (org)</h3>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy === `org-${plan.priceId}`}
                    onClick={() => orgCheckout(plan.priceId)}
                  >
                    Subscribe org
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="card">
        <h2>Plans</h2>
        {!configured ? (
          <p className="muted">Plans appear here after <code>SAAS_STRIPE_*</code> is set in <code>backend/.env</code>.</p>
        ) : !subscription?.isActive ? (
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
    </div>
  );
}
