import { FormEvent, useEffect, useState } from "react";

import { stripeConfigApi, type StripeConfig } from "../api/client";

type Props = {
  projectSlug: string;
  hasLocalPath: boolean;
  onError: (msg: string) => void;
};

export default function StripeConfigPanel({ projectSlug, hasLocalPath, onError }: Props) {
  const [config, setConfig] = useState<StripeConfig | null>(null);
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!hasLocalPath) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await stripeConfigApi.get(projectSlug);
      setConfig(data.config);
      setExists(data.exists);
      onError("");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load stripe config");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [projectSlug, hasLocalPath]);

  function updateTier(index: number, field: "name" | "amount", value: string) {
    if (!config) return;
    const tiers = config.tiers.map((tier, i) =>
      i === index
        ? {
            ...tier,
            [field]: field === "amount" ? Number(value) || 0 : value,
          }
        : tier
    );
    setConfig({ ...config, tiers });
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!config) return;
    setBusy(true);
    onError("");
    try {
      const data = await stripeConfigApi.save(projectSlug, config);
      setConfig(data.config);
      setExists(true);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (!hasLocalPath) {
    return (
      <section className="card">
        <h2>Stripe config</h2>
        <p className="muted">Set a local path to edit stripe.config.json (catalog tiers, app URL).</p>
      </section>
    );
  }

  if (loading || !config) {
    return (
      <section className="card">
        <h2>Stripe config</h2>
        <p className="muted">{loading ? "Loading…" : "Could not load config."}</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>Stripe config</h2>
      <p className="muted">
        {exists ? "stripe.config.json in project root" : "No file yet — save to create stripe.config.json"}
      </p>
      <form className="settings-form compact" onSubmit={onSave}>
        <label>
          App URL
          <input
            value={config.appUrl}
            onChange={(e) => setConfig({ ...config, appUrl: e.target.value })}
            placeholder="http://localhost:3000"
          />
        </label>
        <fieldset className="tier-fieldset">
          <legend>Pricing tiers</legend>
          {config.tiers.map((tier, index) => (
            <div key={`${tier.name}-${index}`} className="tier-row">
              <input
                value={tier.name}
                onChange={(e) => updateTier(index, "name", e.target.value)}
                placeholder="Tier name"
                aria-label={`Tier ${index + 1} name`}
              />
              <input
                type="number"
                value={tier.amount}
                onChange={(e) => updateTier(index, "amount", e.target.value)}
                placeholder="Amount (cents)"
                aria-label={`Tier ${index + 1} amount`}
              />
              <span className="muted">{tier.interval}</span>
            </div>
          ))}
        </fieldset>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Save stripe.config.json"}
        </button>
      </form>
    </section>
  );
}
