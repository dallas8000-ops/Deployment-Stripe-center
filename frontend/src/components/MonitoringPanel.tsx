import { useEffect, useState } from "react";

import {
  monitoringApi,
  projectsApi,
  type AuditEntry,
  type DriftItem,
  type DriftResult,
  type WebhookHealthResult,
} from "../api/client";

type LastDriftSnapshot = {
  driftCount: number;
  checkedAt?: string;
  items?: DriftItem[];
};

type Props = {
  projectSlug: string;
  lastDrift?: LastDriftSnapshot | null;
  onResynced?: () => void;
};

export default function MonitoringPanel({ projectSlug, lastDrift, onResynced }: Props) {
  const [drift, setDrift] = useState<DriftResult | null>(null);
  const [webhook, setWebhook] = useState<WebhookHealthResult | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (lastDrift && !drift) {
      setDrift({
        driftCount: lastDrift.driftCount,
        items: lastDrift.items || [],
        manifestPriceCount: 0,
        checkedAt: lastDrift.checkedAt,
      });
    }
  }, [lastDrift, drift]);

  async function loadAudit() {
    try {
      const res = await projectsApi.audit(projectSlug);
      setAudit(res.entries);
    } catch {
      /* optional */
    }
  }

  useEffect(() => {
    loadAudit();
  }, [projectSlug]);

  async function loadDrift() {
    setLoading("drift");
    setError("");
    try {
      setDrift(await monitoringApi.drift(projectSlug));
      await loadAudit();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Drift check failed");
    } finally {
      setLoading("");
    }
  }

  async function runResync() {
    setLoading("resync");
    setError("");
    try {
      const res = await monitoringApi.driftResync(projectSlug);
      setDrift(res.after);
      onResynced?.();
      await loadAudit();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-sync failed");
    } finally {
      setLoading("");
    }
  }

  async function loadWebhookHealth() {
    setLoading("webhook");
    setError("");
    try {
      setWebhook(await monitoringApi.webhookHealth(projectSlug));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Webhook health failed");
    } finally {
      setLoading("");
    }
  }

  const displayDrift = drift;

  return (
    <section className="card monitoring-card">
      <div className="card-header-row">
        <h2>Monitoring</h2>
        <span className="pipeline-hint">Catalog drift · webhook health</span>
      </div>
      <p className="muted">
        Compare manifest vs live Stripe catalog. Drift checks run every 6 hours when Celery Beat is enabled.
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="copilot-actions">
        <button type="button" className="btn btn-secondary" onClick={loadDrift} disabled={!!loading}>
          {loading === "drift" ? "Checking…" : "Check catalog drift"}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={runResync}
          disabled={!!loading}
          title="Re-provision Stripe catalog and webhooks from config"
        >
          {loading === "resync" ? "Re-syncing…" : "Re-sync Stripe"}
        </button>
        <button type="button" className="btn btn-secondary" onClick={loadWebhookHealth} disabled={!!loading}>
          {loading === "webhook" ? "Checking…" : "Webhook health"}
        </button>
      </div>

      {displayDrift && (
        <div className="copilot-result">
          <h3>
            Catalog drift
            {displayDrift.driftCount === 0 ? (
              <span className="badge badge-ok">In sync</span>
            ) : (
              <span className="badge badge-warn">{displayDrift.driftCount} issue(s)</span>
            )}
          </h3>
          {displayDrift.checkedAt && (
            <p className="muted">Last checked {new Date(displayDrift.checkedAt).toLocaleString()}</p>
          )}
          {displayDrift.items.length === 0 ? (
            <p className="muted">No drift detected between manifest and Stripe.</p>
          ) : (
            <ul className="drift-list">
              {displayDrift.items.map((item) => (
                <li
                  key={`${item.category}-${item.message}`}
                  className={`drift-item severity-${item.severity}`}
                >
                  <strong>{item.category}</strong> — {item.message}
                  {item.fix && <p className="muted fix-hint">{item.fix}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {webhook && (
        <div className="copilot-result">
          <h3>
            Webhook health
            {webhook.healthy ? (
              <span className="badge badge-ok">Healthy</span>
            ) : (
              <span className="badge badge-warn">Issues found</span>
            )}
          </h3>
          {webhook.expectedWebhookUrl && (
            <p className="muted">
              Expected URL: <code>{webhook.expectedWebhookUrl}</code>
            </p>
          )}
          {webhook.endpoints.length > 0 && (
            <ul className="drift-list">
              {webhook.endpoints.map((ep) => (
                <li key={ep.id}>
                  <code>{ep.url}</code> — {ep.status}
                  {ep.matchesExpected === true && " · matches expected"}
                  {ep.matchesExpected === false && " · URL mismatch"}
                </li>
              ))}
            </ul>
          )}
          {Object.keys(webhook.recentEventTypes).length > 0 && (
            <details className="handoff-details">
              <summary>Recent event types</summary>
              <ul className="drift-list compact">
                {Object.entries(webhook.recentEventTypes).map(([type, count]) => (
                  <li key={type}>
                    {type}: {count}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {webhook.issues.length > 0 && (
            <ul className="drift-list">
              {webhook.issues.map((issue) => (
                <li key={issue.message} className={`drift-item severity-${issue.severity}`}>
                  {issue.message}
                  {issue.fix && <p className="muted fix-hint">{issue.fix}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {audit.length > 0 && (
        <div className="copilot-result">
          <h3>Audit log</h3>
          <ul className="audit-list">
            {audit.slice(0, 8).map((entry) => (
              <li key={entry.id}>
                <span className="audit-action">{entry.action}</span>
                <span className="muted">
                  {new Date(entry.created_at).toLocaleString()}
                  {entry.actor ? ` · ${entry.actor}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
