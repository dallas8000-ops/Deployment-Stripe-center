import { useCallback, useEffect, useState } from "react";

import { setupHubApi, type SetupHubStatus } from "../api/client";
import { APP_SHORT_NAME } from "../config/branding";

type Props = {
  projectSlug: string;
  onRunFullSetup?: () => void;
  pipelineRunning?: boolean;
  onVaultChanged?: () => void;
};

export default function SetupHubPanel({
  projectSlug,
  onRunFullSetup,
  pipelineRunning = false,
  onVaultChanged,
}: Props) {
  const [status, setStatus] = useState<SetupHubStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [clearVaultOnReset, setClearVaultOnReset] = useState(false);
  const [lastAction, setLastAction] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setStatus(await setupHubApi.status(projectSlug));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load setup status");
    } finally {
      setLoading(false);
    }
  }, [projectSlug]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function runReset() {
    const msg = clearVaultOnReset
      ? "Reset workspace and clear all vault secrets? You will need to re-enter Stripe keys."
      : "Reset workspace metadata, portfolio registry, and stripe.config.json?";
    if (!window.confirm(msg)) return;

    setBusy("reset");
    setError("");
    setLastAction("");
    try {
      const result = await setupHubApi.reset(projectSlug, clearVaultOnReset);
      if (result.status) setStatus(result.status);
      setLastAction(
        result.vaultSecretsCleared
          ? `Workspace reset. Cleared ${result.vaultSecretsCleared} vault secret(s).`
          : "Workspace reset — registry and stripe.config.json refreshed."
      );
      onVaultChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setBusy("");
    }
  }

  async function runAudit() {
    setBusy("audit");
    setError("");
    setLastAction("");
    try {
      const result = await setupHubApi.audit(projectSlug);
      if (result.status) setStatus(result.status);
      const summary = result.audit?.summary as Record<string, number> | undefined;
      setLastAction(
        summary
          ? `Stripe scan complete — ${summary.endpointCount ?? 0} webhook(s), ${summary.failingCount ?? 0} failing.`
          : "Stripe account scan complete."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stripe scan failed");
    } finally {
      setBusy("");
    }
  }

  async function runSyncVault() {
    setBusy("sync-vault");
    setError("");
    setLastAction("");
    try {
      const result = await setupHubApi.syncVaultToProjects(projectSlug);
      if (result.status) setStatus(result.status);
      const rows = (result.results as Array<{ projectSlug?: string; copiedKeys?: string[] }>) || [];
      const copied = rows.filter((r) => (r.copiedKeys?.length ?? 0) > 0).length;
      setLastAction(
        copied
          ? `Copied Stripe keys to ${copied} billing project(s) (server-side — secret key never shown in UI).`
          : "All billing projects already have keys, or hub vault is empty — add keys in Secure Vault first."
      );
      onVaultChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Vault sync failed");
    } finally {
      setBusy("");
    }
  }

  async function runRegisterWebhooks(dryRun: boolean) {
    setBusy(dryRun ? "preview" : "webhooks");
    setError("");
    setLastAction("");
    try {
      const result = await setupHubApi.registerWebhooks(projectSlug, dryRun);
      if (result.status) setStatus(result.status);
      const rows = result.results || [];
      if (dryRun) {
        setLastAction(
          rows.length
            ? `Preview: would register ${rows.length} webhook(s).`
            : "Preview: no registry apps need registration."
        );
      } else {
        const okCount = rows.filter((r) => r.ok).length;
        setLastAction(`Registered ${okCount}/${rows.length} webhook(s). Copy whsec_ to Railway if new.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Webhook registration failed");
    } finally {
      setBusy("");
    }
  }

  const mode = status?.verification?.secretKey?.mode;

  return (
    <section className="card setup-hub-card">
      <div className="card-header-row">
        <div>
          <h2>Setup Hub</h2>
          <p className="muted">
            One place to rename, reset, scan Stripe, register webhooks, and run the full pipeline — no CLI required.
          </p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void refresh()} disabled={loading}>
          Refresh
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {lastAction && <div className="alert">{lastAction}</div>}

      {status && !status.isHubProject && (
        <div className="alert">
          Stripe keys are pulled automatically from <strong>Automation Center</strong> when you open this page,
          verify, or run setup. Expected webhook URL is for <strong>{status.projectName}</strong>, not the hub.
        </div>
      )}

      {status?.portfolioSummary && (
        <div className="setup-meta muted">
          <p>
            Portfolio: <strong>{status.portfolioSummary.stripeBillingCount}</strong> Stripe billing apps in registry.
            Kistie Store, Blog API, and React Store Catalog are portfolio-only (hidden from this list).
            API Transfer is merged into Automation Center.
          </p>
        </div>
      )}

      {status?.stripeExempt && (
        <div className="alert">
          This project is <strong>Stripe exempt</strong> — portfolio demo only, no subscription billing or webhooks
          required.
        </div>
      )}

      {loading && !status ? (
        <p className="muted">Loading setup checklist…</p>
      ) : (
        <>
          <ul className="provider-list setup-checklist">
            {(status?.steps || []).map((step) => (
              <li key={step.id}>
                <span className={`badge ${step.ok ? "badge-ok" : "badge-warn"}`}>{step.ok ? "OK" : "Todo"}</span>
                <strong>{step.label}</strong>
                <span className="muted">{step.detail}</span>
              </li>
            ))}
          </ul>

          {status && (
            <div className="setup-meta muted">
              <p>
                Production URL: <code>{status.productionUrl}</code>
              </p>
              <p>
                Expected webhook: <code>{status.expectedWebhookUrl}</code>
              </p>
              {mode && mode !== "unknown" && (
                <p>
                  Stripe mode: <strong>{mode}</strong>
                </p>
              )}
            </div>
          )}

          <div className="page-actions compact-actions setup-actions">
            <button type="button" className="btn btn-secondary" onClick={runReset} disabled={!!busy}>
              {busy === "reset" ? "Resetting…" : "1. Reset workspace"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={runAudit} disabled={!!busy}>
              {busy === "audit" ? "Scanning…" : "2. Scan Stripe account"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void runRegisterWebhooks(false)}
              disabled={!!busy}
            >
              {busy === "webhooks" ? "Registering…" : "3. Register webhooks"}
            </button>
            {onRunFullSetup && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={onRunFullSetup}
                disabled={!!busy || pipelineRunning || !status?.readyForPipeline}
                title={
                  status?.readyForPipeline
                    ? `Run ${APP_SHORT_NAME} pipeline`
                    : "Add valid Stripe keys to the vault first"
                }
              >
                {pipelineRunning ? "Pipeline running…" : "4. Run full setup"}
              </button>
            )}
          </div>

          <div className="page-actions compact-actions">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => void runSyncVault()} disabled={!!busy}>
              {busy === "sync-vault" ? "Syncing…" : "Sync keys to billing projects"}
            </button>
          </div>

          <label className="toggle-inline setup-reset-option">
            <input
              type="checkbox"
              checked={clearVaultOnReset}
              onChange={(e) => setClearVaultOnReset(e.target.checked)}
            />
            Clear vault secrets when resetting (start fresh)
          </label>

          {status?.lastPortfolioAuditRegistryGaps && status.lastPortfolioAuditRegistryGaps.length > 0 && (
            <div className="alert alert-error">
              <strong>Missing Stripe webhooks</strong>
              <ul>
                {status.lastPortfolioAuditRegistryGaps.map((gap) => (
                  <li key={`${gap.app}-${gap.expectedUrl}`}>
                    {gap.app}: {gap.issue}
                    {gap.expectedUrl && (
                      <>
                        {" "}
                        — <code>{gap.expectedUrl}</code>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
