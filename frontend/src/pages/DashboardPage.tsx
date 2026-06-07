import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { projectsApi, type Project } from "../api/client";
import ScoreRing from "../components/ScoreRing";

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [creating, setCreating] = useState(false);

  const stats = useMemo(() => {
    const scores = projects
      .map((p) => p.latest_readiness_score)
      .filter((s): s is number => typeof s === "number");
    const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
    const running = projects.filter((p) => p.last_run_status === "running").length;
    return { avg, running, total: projects.length };
  }, [projects]);

  async function load() {
    setLoading(true);
    try {
      setProjects(await projectsApi.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      await projectsApi.create({ name, local_path: localPath || undefined });
      setName("");
      setLocalPath("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Projects</h1>
          <p className="muted">Manage Stripe integrations for your apps.</p>
        </div>
        <Link to="/billing" className="btn btn-secondary">
          Billing
        </Link>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <section className="stats-row">
        <div className="stat-card">
          <span className="muted">Projects</span>
          <strong>{stats.total}</strong>
        </div>
        <div className="stat-card">
          <span className="muted">Avg readiness</span>
          <div className="stat-with-ring">
            <ScoreRing score={stats.avg} size={52} />
          </div>
        </div>
        <div className="stat-card">
          <span className="muted">Running pipelines</span>
          <strong>{stats.running}</strong>
        </div>
      </section>

      <section className="card">
        <h2>New project</h2>
        <form className="form-row" onSubmit={onCreate}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Local path (for scan)
            <input
              value={localPath}
              onChange={(e) => setLocalPath(e.target.value)}
              placeholder="C:\path\to\repo"
            />
          </label>
          <button type="submit" className="btn btn-primary" disabled={creating}>
            {creating ? "Creating…" : "Create project"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Your projects</h2>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : projects.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-title">No projects yet</p>
            <p className="muted">Create a project above, set a local path, then unlock the vault and run the pipeline.</p>
          </div>
        ) : (
          <ul className="project-grid">
            {projects.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${p.slug}`} className="project-card">
                  <div className="project-card-top">
                    <strong>{p.name}</strong>
                    <ScoreRing score={p.latest_readiness_score ?? null} size={48} />
                  </div>
                  <div className="project-card-meta">
                    <span className="pill">{p.framework}</span>
                    <span className="muted">{p.language}</span>
                    {p.last_run_status && (
                      <span className={`run-pill run-${p.last_run_status}`}>{p.last_run_status}</span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
