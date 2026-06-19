import { useState } from "react";

import { healthApi, type StripeAdvisorReport } from "../api/client";

type Props = {
  projectSlug: string;
};

const WHERE_LABEL: Record<string, string> = {
  stripe_dashboard: "Stripe Dashboard",
  hosting: "Hosting (Railway / Render)",
  vault: "Stripe Installer vault",
  installer: "Stripe Installer",
};

function severityClass(severity: string) {
  if (severity === "error") return "issue-error";
  if (severity === "warning") return "issue-warn";
  return "issue-info";
}

export default function StripeAdvisorPanel({ projectSlug }: Props) {
  const [report, setReport] = useState<StripeAdvisorReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAdvisor() {
    setLoading(true);
    setError("");
    try {
      setReport(await healthApi.stripeAdvisor(projectSlug));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Advisor scan failed");
    } finally {
      setLoading(false);
    }
  }

  const links = report?.dashboardLinks;

  return (
    <section className="card advisor-card">
      <div className="card-header-row">
        <div>
          <h2>Stripe webhook advisor</h2>
          <p className="muted">
            Find why Dashboard shows 100% webhook errors — hosting vs Stripe vs secrets — with step-by-step fixes.
          </p>
        </div>
      </div>

      <div className="page-actions compact-actions">
        <button type="button" className="btn btn-primary" onClick={runAdvisor} disabled={loading}>
          {loading ? "Scanning…" : report ? "Confirm / re-scan" : "Run webhook advisor"}
        </button>
        {links && (
          <>
            <a
              href={links.keys}
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary"
            >
              Open API keys
            </a>
            <a
              href={links.webhooks}
              target="_blank"
              rel="noreferrer"
              className="btn btn-secondary"
            >
              Open webhooks
            </a>
          </>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {report?.webhookErrorRisk && (
        <div className="alert alert-error">
          <strong>Webhook delivery at risk</strong> — Stripe may show 100% failed deliveries until this is resolved.
          Primary issue: <code>{report.primaryRootCause}</code>
        </div>
      )}

      {report && !report.webhookErrorRisk && report.primaryRootCause === "HEALTHY" && (
        <div className="alert" style={{ borderColor: "var(--ok, #2d6a4f)" }}>
          Webhooks look healthy. Re-scan after deploy or Dashboard changes.
        </div>
      )}

      {report && <p className="diagnose-summary">{report.summary}</p>}

      {report && report.findings.length > 0 && (
        <ul className="issue-list">
          {report.findings.map((finding) => (
            <li
              key={finding.rootCause}
              className={`issue-item ${severityClass(finding.severity)}`}
            >
              <div className="issue-main">
                <strong>{finding.title}</strong>
                <span className="issue-badge">{finding.rootCause}</span>
              </div>
              <p>{finding.summary}</p>
              {finding.playbook.length > 0 && (
                <ol className="advisor-playbook">
                  {finding.playbook.map((step) => (
                    <li key={`${finding.rootCause}-${step.order}`}>
                      <strong>
                        {step.order}. {step.title}
                      </strong>
                      <span className="issue-badge">{WHERE_LABEL[step.where] || step.where}</span>
                      <p className="muted">{step.detail}</p>
                      {step.url && (
                        <a href={step.url} target="_blank" rel="noreferrer" className="btn btn-sm btn-secondary">
                          Open link
                        </a>
                      )}
                      {step.confirm && (
                        <p className="vault-hint">
                          Confirm: {step.confirm}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </li>
          ))}
        </ul>
      )}

      {typeof report?.checks?.expectedWebhookUrl === "string" && (
        <p className="vault-hint">
          Expected webhook: <code>{report.checks.expectedWebhookUrl}</code>
        </p>
      )}
    </section>
  );
}
