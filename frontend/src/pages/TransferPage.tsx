import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { transferApi, type TransferProviderStatus } from "../api/client";

export default function TransferPage() {
  const [providers, setProviders] = useState<TransferProviderStatus[]>([]);
  const [moduleStatus, setModuleStatus] = useState<string>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mod = await transferApi.moduleStatus();
        const prov = await transferApi.providerStatus();
        if (!cancelled) {
          setModuleStatus(mod.status);
          setProviders(prov.providers);
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
          API Transfer deploy pipeline — shared projects and vault with Stripe Installer.
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
          Per-project deploy: open a project workspace → use API{" "}
          <code>POST /api/v1/projects/&#123;slug&#125;/transfer/deploy/</code>
        </p>
      </section>

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
          <li>Deployment history and status refresh per project</li>
          <li>Railway env backup</li>
          <li className="muted">Next: Render→Railway transfer runs, transfer UI in project workspace</li>
        </ul>
        <p>
          <Link to="/">Back to projects</Link>
        </p>
      </section>
    </div>
  );
}
