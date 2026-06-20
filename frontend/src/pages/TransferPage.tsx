import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { transferApi, type TransferProviderStatus } from "../api/client";

export default function TransferPage() {
  const [providers, setProviders] = useState<TransferProviderStatus[]>([]);
  const [moduleStatus, setModuleStatus] = useState<string>("loading");
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [auditValid, setAuditValid] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [mod, prov, metricData, auditData] = await Promise.all([
          transferApi.moduleStatus(),
          transferApi.providerStatus(),
          transferApi.transferMetrics(),
          transferApi.transferAudit(),
        ]);
        if (!cancelled) {
          setModuleStatus(mod.status);
          setProviders(prov.providers);
          setMetrics(metricData.summary as Record<string, unknown>);
          setAuditValid(Boolean(auditData.valid?.valid));
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load transfer status");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Deployments &amp; transfer</h1>
        <p className="muted">
          Deployment &amp; transfer pipeline — shared projects and vault with Stripe setup.
        </p>
      </div>

      {error && (
        <section className="card card-error">
          <p>{error}</p>
        </section>
      )}

      <section className="card">
        <h2>Module status</h2>
        <p>
          <strong>api_transfer</strong>: {moduleStatus}
        </p>
        <p className="muted">
          Per-project deploy and Render→Railway migration: open a project workspace →{" "}
          <strong>API Transfer</strong> section.
        </p>
      </section>

      {metrics && (
        <section className="card">
          <h2>Transfer queue</h2>
          <ul className="provider-list">
            <li>
              <strong>Running</strong> {String(metrics.running ?? 0)}
            </li>
            <li>
              <strong>Queued</strong> {String(metrics.queued ?? 0)}
            </li>
            <li>
              <strong>Retryable</strong> {String(metrics.retryable ?? 0)}
            </li>
            <li>
              <strong>Dead letter</strong> {String(metrics.deadLetter ?? 0)}
            </li>
          </ul>
          <p className="muted">
            Process queued jobs with <code>npm run transfer:worker</code> in a second terminal.
          </p>
        </section>
      )}

      {auditValid !== null && (
        <section className="card">
          <h2>Audit chain</h2>
          <p>
            Tamper-evident log:{" "}
            <span className={`badge ${auditValid ? "badge-ok" : "badge-warn"}`}>
              {auditValid ? "Valid" : "Broken — investigate"}
            </span>
          </p>
        </section>
      )}

      <section className="card">
        <h2>Provider readiness</h2>
        {providers.length === 0 ? (
          <p className="muted">Loading providers…</p>
        ) : (
          <ul className="provider-list">
            {providers.map((p) => (
              <li key={p.provider}>
                <strong>{p.provider}</strong>
                <span className={`badge ${p.liveEnabled ? "badge-ok" : "badge-warn"}`}>
                  {p.status}
                </span>
                <span className="muted">{p.message}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="muted">
          Platform tokens: <code>private_env/railway.env</code>, <code>render.env</code>,{" "}
          <code>github.env</code> (local) or project vault keys.
        </p>
      </section>

      <section className="card">
        <h2>What&apos;s merged vs planned</h2>
        <ul>
          <li>GitHub import, framework detect, Railway/Render/Fly deploy pipeline</li>
          <li>Render→Railway migration runs + worker (<code>npm run transfer:worker</code>)</li>
          <li>Deployment history, Railway env backup, platform setup audit</li>
          <li>Transfer UI on each project workspace</li>
          <li className="muted">Planned: discover/plan/apply, Terraform, console bootstrap, client prewire</li>
        </ul>
        <p>
          Production cutover (Railway, Stripe, domain): see <code>docs/CUTOVER.md</code>
        </p>
        <p>
          <Link to="/">Back to projects</Link>
        </p>
      </section>
    </div>
  );
}
