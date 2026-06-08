import { useState } from "react";

import { projectsApi, type GithubCiStatus } from "../api/client";

type Props = {
  projectSlug: string;
  hasGitUrl: boolean;
  onError: (msg: string) => void;
};

export default function CiGatePanel({ projectSlug, hasGitUrl, onError }: Props) {
  const [ci, setCi] = useState<GithubCiStatus | null>(null);
  const [gate, setGate] = useState<{ passed: boolean; score: number; label: string } | null>(null);
  const [workflow, setWorkflow] = useState("");
  const [loading, setLoading] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);

  async function loadCi() {
    if (!hasGitUrl) return;
    setLoading("ci");
    onError("");
    try {
      setCi(await projectsApi.githubCiStatus(projectSlug));
    } catch (err) {
      onError(err instanceof Error ? err.message : "CI status failed");
    } finally {
      setLoading("");
    }
  }

  async function runGate() {
    setLoading("gate");
    onError("");
    try {
      const res = await projectsApi.readinessGate(projectSlug);
      setGate({ passed: res.passed, score: res.score, label: res.label });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Readiness gate failed");
    } finally {
      setLoading("");
    }
  }

  async function loadWorkflow() {
    setLoading("workflow");
    onError("");
    try {
      const res = await projectsApi.ciWorkflow(projectSlug);
      setWorkflow(res.workflow);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load workflow");
    } finally {
      setLoading("");
    }
  }

  async function createApiKey() {
    setLoading("key");
    onError("");
    try {
      const res = await projectsApi.createApiKey(projectSlug, "GitHub Actions");
      setNewKey(res.key);
    } catch (err) {
      onError(err instanceof Error ? err.message : "API key create failed");
    } finally {
      setLoading("");
    }
  }

  return (
    <section className="card ci-gate-card">
      <div className="card-header-row">
        <h2>CI gate</h2>
        <span className="pipeline-hint">GitHub Actions · readiness API</span>
      </div>
      <p className="muted">
        Block merges until Stripe readiness passes. Use a project API key in GitHub repository secrets.
      </p>

      <div className="copilot-actions">
        <button type="button" className="btn btn-secondary" onClick={runGate} disabled={!!loading}>
          {loading === "gate" ? "Checking…" : "Run readiness gate"}
        </button>
        {hasGitUrl && (
          <button type="button" className="btn btn-secondary" onClick={loadCi} disabled={!!loading}>
            {loading === "ci" ? "Loading…" : "GitHub CI status"}
          </button>
        )}
        <button type="button" className="btn btn-secondary" onClick={loadWorkflow} disabled={!!loading}>
          {loading === "workflow" ? "Loading…" : "Show workflow YAML"}
        </button>
        <button type="button" className="btn btn-primary" onClick={createApiKey} disabled={!!loading}>
          {loading === "key" ? "Creating…" : "Create CI API key"}
        </button>
      </div>

      {gate && (
        <div className="copilot-result">
          <h3>
            Readiness gate
            {gate.passed ? (
              <span className="badge badge-ok">Passed · {gate.score}</span>
            ) : (
              <span className="badge badge-warn">Failed · {gate.score}</span>
            )}
          </h3>
          <p className="muted">{gate.label}</p>
        </div>
      )}

      {ci && (
        <div className="copilot-result">
          <h3>
            GitHub CI — {ci.ref}
            {ci.success ? (
              <span className="badge badge-ok">{ci.state}</span>
            ) : (
              <span className="badge badge-warn">{ci.state}</span>
            )}
          </h3>
          <p className="muted">{ci.repository}</p>
          {ci.checkRuns.length > 0 && (
            <ul className="drift-list compact">
              {ci.checkRuns.map((run) => (
                <li key={run.name || run.htmlUrl}>
                  {run.name}: {run.status} {run.conclusion ? `(${run.conclusion})` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {newKey && (
        <div className="alert alert-info">
          <strong>Save this API key now</strong> — it won&apos;t be shown again.
          <pre className="verify-pre">{newKey}</pre>
          <p className="muted">
            Add secrets: <code>STRIPE_INSTALLER_URL</code>, <code>STRIPE_INSTALLER_PROJECT</code>,{" "}
            <code>STRIPE_INSTALLER_API_KEY</code>
          </p>
        </div>
      )}

      {workflow && (
        <details className="handoff-details">
          <summary>.github/workflows/stripe-installer.yml</summary>
          <pre className="verify-pre">{workflow}</pre>
        </details>
      )}
    </section>
  );
}
