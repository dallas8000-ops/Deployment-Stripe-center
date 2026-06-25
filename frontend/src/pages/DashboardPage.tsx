import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { projectsApi, type Project } from "../api/client";
import { filterVisibleProjects, PORTFOLIO_DEMOS } from "../config/portfolio";
import ScoreRing from "../components/ScoreRing";
import WelcomeWizard from "../components/WelcomeWizard";

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [portfolioProjects, setPortfolioProjects] = useState<Record<string, Project>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [gitUrl, setGitUrl] = useState("");
  const [creating, setCreating] = useState(false);
  const [wizardDismissed, setWizardDismissed] = useState(
    () => localStorage.getItem("wizard-dismissed") === "true"
  );

  const visibleProjects = useMemo(() => filterVisibleProjects(projects), [projects]);

  const stats = useMemo(() => {
    const scores = visibleProjects
      .map((p) => p.latest_readiness_score)
      .filter((s): s is number => typeof s === "number");
    const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
    const running = visibleProjects.filter((p) => p.last_run_status === "running").length;
    return { avg, running, total: visibleProjects.length };
  }, [visibleProjects]);

  async function loadPortfolioProjects() {
    const entries = await Promise.all(
      PORTFOLIO_DEMOS.map(async (demo) => {
        try {
          const project = await projectsApi.get(demo.slug);
          return [demo.slug, project] as const;
        } catch {
          return [demo.slug, null] as const;
        }
      })
    );
    const mapped: Record<string, Project> = {};
    for (const [slug, project] of entries) {
      if (project) mapped[slug] = project;
    }
    setPortfolioProjects(mapped);
  }

  async function load() {
    setLoading(true);
    try {
      const [listed] = await Promise.all([projectsApi.list(), loadPortfolioProjects()]);
      setProjects(listed);
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
    if (!localPath.trim()) {
      setError("Set the local path to your real app folder before creating a project.");
      return;
    }
    setCreating(true);
    setError("");
    try {
      await projectsApi.create({
        name,
        local_path: localPath.trim(),
        git_url: gitUrl || undefined,
      });
      setName("");
      setLocalPath("");
      setGitUrl("");
      localStorage.setItem("wizard-dismissed", "true");
      setWizardDismissed(true);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  function handleWizardComplete() {
    localStorage.setItem("wizard-dismissed", "true");
    setWizardDismissed(true);
  }

  return (
    <>
      {!loading && projects.length === 0 && !wizardDismissed && (
        <WelcomeWizard onComplete={handleWizardComplete} />
      )}
      <div className="page">
      <div className="page-header">
        <div>
          <h1>Projects</h1>
          <p className="muted">
            Stripe setup runs in each app&apos;s own folder — open that folder in your editor to write code.
          </p>
        </div>
        {!loading && stats.total > 0 && (
          <div className="stats-row">
            <span>{stats.total} projects</span>
            {stats.avg !== null && <span>Avg readiness {stats.avg}</span>}
            {stats.running > 0 && <span>{stats.running} running</span>}
          </div>
        )}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <section className="card">
        <h2>Portfolio demos (Railway storefronts)</h2>
        <p className="muted">
          Stripe-exempt portfolio apps — not listed under billing projects. Open SilverFox here to push Railway env
          vars and run full deploy setup (not the Automation Center hub).
        </p>
        <ul className="project-grid">
          {PORTFOLIO_DEMOS.map((demo) => {
            const existing = portfolioProjects[demo.slug];
            return (
              <li key={demo.slug}>
                <div className="project-card">
                  {existing ? (
                    <Link to={`/projects/${demo.slug}`} className="project-card-link">
                      <div className="project-card-top">
                        <strong>{demo.name}</strong>
                        <ScoreRing score={existing.latest_readiness_score ?? null} size={48} />
                      </div>
                      <div className="project-card-meta">
                        <span className="pill">portfolio</span>
                        <span className="muted">{demo.note}</span>
                      </div>
                    </Link>
                  ) : (
                    <div className="project-card-link">
                      <div className="project-card-top">
                        <strong>{demo.name}</strong>
                      </div>
                      <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.85rem" }}>
                        Not registered yet — create below with slug <code>{demo.slug}</code>
                        {demo.localPath ? (
                          <>
                            {" "}
                            and path <code>{demo.localPath}</code>
                          </>
                        ) : null}
                      </p>
                    </div>
                  )}
                  {existing && (
                    <Link to={`/projects/${demo.slug}/settings`} className="project-card-settings">
                      Edit settings
                    </Link>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="card">
        <h2>New project</h2>
        <form className="settings-form" onSubmit={onCreate}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Local path
            <input
              value={localPath}
              onChange={(e) => setLocalPath(e.target.value)}
              placeholder="C:\Software Projects\YourApp"
              required
            />
          </label>
          <p className="muted" style={{ marginTop: "-0.5rem" }}>
            Your app&apos;s real folder on disk. Setup and Stripe files are written here — not inside this hub repo.
          </p>
          <label>
            Git URL (optional)
            <input
              value={gitUrl}
              onChange={(e) => setGitUrl(e.target.value)}
              placeholder="https://github.com/org/repo"
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
        ) : visibleProjects.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-title">No projects yet</p>
            <p className="muted">Create a project above with your real local path, then unlock the vault and run the pipeline.</p>
          </div>
        ) : (
          <ul className="project-grid">
            {visibleProjects.map((p) => (
              <li key={p.id}>
                <div className="project-card">
                  <Link to={`/projects/${p.slug}`} className="project-card-link">
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
                  <Link to={`/projects/${p.slug}/settings`} className="project-card-settings">
                    Edit settings
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
    </>
  );
}
