import ScoreRing from "./ScoreRing";

export interface ReadinessCheck {
  id: string;
  category: string;
  name: string;
  status: "pass" | "warn" | "fail";
  message: string;
  fix?: string | null;
}

type ReadinessPanelProps = {
  score: number | null;
  label?: string;
  checks: ReadinessCheck[];
  loading?: boolean;
};

function statusIcon(status: string) {
  if (status === "pass") return "✓";
  if (status === "warn") return "!";
  return "✗";
}

export default function ReadinessPanel({ score, label, checks, loading }: ReadinessPanelProps) {
  const categories = [...new Set(checks.map((c) => c.category))];

  return (
    <section className="card readiness-card">
      <div className="readiness-header">
        <div>
          <h2>Production readiness</h2>
          <p className="muted">Deploy score — pass/warn/fail weighted checks</p>
        </div>
        <ScoreRing score={score} label="/100" sublabel={label} />
      </div>

      {loading ? (
        <p className="muted">Running checks…</p>
      ) : checks.length === 0 ? (
        <p className="muted">Run readiness to see deployment checks.</p>
      ) : (
        <div className="check-groups">
          {categories.map((cat) => (
            <div key={cat} className="check-group">
              <h3>{cat}</h3>
              <ul className="check-list">
                {checks
                  .filter((c) => c.category === cat)
                  .map((check) => (
                    <li key={check.id} className={`check-item check-${check.status}`}>
                      <span className="check-icon">{statusIcon(check.status)}</span>
                      <div>
                        <strong>{check.name}</strong>
                        <p>{check.message}</p>
                        {check.fix && check.status !== "pass" && (
                          <p className="check-fix">Fix: {check.fix}</p>
                        )}
                      </div>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
