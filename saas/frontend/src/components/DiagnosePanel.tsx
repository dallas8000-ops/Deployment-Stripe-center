import ScoreRing from "./ScoreRing";

export interface StripeIssue {
  id: string;
  category: string;
  severity: "error" | "warning" | "info";
  title: string;
  message: string;
  fix_hint: string;
  auto_fixable: boolean;
  fix_action?: string | null;
}

export interface DiagnosticReport {
  scannedAt: string;
  projectName: string;
  healthScore: number;
  issues: StripeIssue[];
  summary: string;
}

type DiagnosePanelProps = {
  report: DiagnosticReport | null;
  loading?: boolean;
  fixing?: string;
  onDiagnose: () => void;
  onFixAll: () => void;
  onFixIssue: (issueId: string, action?: string | null) => void;
};

function severityClass(severity: string) {
  if (severity === "error") return "issue-error";
  if (severity === "warning") return "issue-warn";
  return "issue-info";
}

export default function DiagnosePanel({
  report,
  loading,
  fixing,
  onDiagnose,
  onFixAll,
  onFixIssue,
}: DiagnosePanelProps) {
  const fixable = report?.issues.filter((i) => i.auto_fixable).length ?? 0;

  return (
    <section className="card diagnose-card">
      <div className="readiness-header">
        <div>
          <h2>Stripe health</h2>
          <p className="muted">Integration diagnostics — keys, files, catalog, webhooks</p>
        </div>
        {report && <ScoreRing score={report.healthScore} label="health" />}
      </div>

      <div className="page-actions compact-actions">
        <button type="button" className="btn btn-secondary" onClick={onDiagnose} disabled={loading}>
          {loading ? "Scanning…" : "Run diagnose"}
        </button>
        {fixable > 0 && (
          <button type="button" className="btn btn-primary" onClick={onFixAll} disabled={!!fixing}>
            {fixing === "all" ? "Fixing…" : `Fix all (${fixable})`}
          </button>
        )}
      </div>

      {report && <p className="diagnose-summary">{report.summary}</p>}

      {report && report.issues.length > 0 ? (
        <ul className="issue-list">
          {report.issues.map((issue) => (
            <li key={issue.id} className={`issue-item ${severityClass(issue.severity)}`}>
              <div className="issue-main">
                <strong>{issue.title}</strong>
                <span className="issue-badge">{issue.category}</span>
              </div>
              <p>{issue.message}</p>
              <p className="muted">{issue.fix_hint}</p>
              {issue.auto_fixable && issue.fix_action && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={!!fixing}
                  onClick={() => onFixIssue(issue.id, issue.fix_action)}
                >
                  {fixing === issue.id ? "Fixing…" : "Fix"}
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : report ? (
        <p className="muted success-text">No issues detected.</p>
      ) : (
        <p className="muted">Run diagnose to scan this project.</p>
      )}
    </section>
  );
}
