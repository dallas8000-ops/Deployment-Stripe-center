import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { orgsApi, projectsApi, type Organization, type Project } from "../api/client";

export default function ProjectSettingsPage() {
  const { slug = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [gitUrl, setGitUrl] = useState("");
  const [productionUrl, setProductionUrl] = useState("");
  const [organizationSlug, setOrganizationSlug] = useState("");
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState("");
  const [cloneMessage, setCloneMessage] = useState("");

  useEffect(() => {
    orgsApi.list().then(setOrgs).catch(() => setOrgs([]));
    projectsApi
      .get(slug)
      .then((p) => {
        setProject(p);
        setName(p.name);
        setDescription(p.description || "");
        setLocalPath(p.local_path || "");
        setGitUrl(p.git_url || "");
        setProductionUrl(p.production_url || "");
        setOrganizationSlug(p.organization_slug || "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [slug]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setBusy("save");
    setError("");
    setSaved(false);
    try {
      const updated = await projectsApi.update(slug, {
        name,
        description,
        local_path: localPath,
        git_url: gitUrl,
        production_url: productionUrl,
        organization_slug: organizationSlug,
      });
      setProject(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy("");
    }
  }

  async function runClone(asyncMode = false) {
    setBusy("clone");
    setError("");
    setCloneMessage("");
    try {
      const result = await projectsApi.clone(slug, { async: asyncMode });
      if (result.status === "queued") {
        setCloneMessage(`Clone queued (task ${result.task_id})`);
      } else {
        setProject(result.project);
        setLocalPath(result.local_path || result.project.local_path || "");
        setCloneMessage(`${result.action === "cloned" ? "Cloned" : "Updated"} → ${result.local_path}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Clone failed");
    } finally {
      setBusy("");
    }
  }

  if (!project) {
    return (
      <div className="page">
        <p className="muted">{error || "Loading…"}</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Project settings</h1>
          <p className="muted">
            <Link to={`/projects/${slug}`}>{project.name}</Link> · paths and production URL for webhooks/readiness
          </p>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {saved && <div className="alert alert-success">Settings saved.</div>}

      <section className="card">
        <form className="settings-form" onSubmit={onSave}>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Description
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </label>
          <label>
            Local path
            <input value={localPath} onChange={(e) => setLocalPath(e.target.value)} placeholder="C:\path\to\repo" />
          </label>
          <label>
            Git URL
            <input value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} placeholder="https://github.com/…" />
          </label>
          {gitUrl && (
            <div className="option-row compact">
              <button type="button" className="btn btn-secondary" onClick={() => runClone(false)} disabled={busy === "clone"}>
                {busy === "clone" ? "Cloning…" : "Clone / pull repo"}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => runClone(true)} disabled={busy === "clone"}>
                Clone async
              </button>
              {cloneMessage && <span className="text-success">{cloneMessage}</span>}
            </div>
          )}
          <p className="muted vault-hint">
            Private repos: store <code>GITHUB_TOKEN</code> or <code>GIT_TOKEN</code> in vault. Docker prod: mount
            SSH key via <code>GIT_SSH_KEY_PATH</code> (see docs/PRODUCTION.md).
          </p>
          <label>
            Organization (agency)
            <select value={organizationSlug} onChange={(e) => setOrganizationSlug(e.target.value)}>
              <option value="">Personal project</option>
              {orgs.map((o) => (
                <option key={o.id} value={o.slug}>
                  {o.name} ({o.my_role})
                </option>
              ))}
            </select>
            <span className="field-hint">Assign to an org so team members can access this project.</span>
          </label>
          <label>
            Production app URL
            <input
              value={productionUrl}
              onChange={(e) => setProductionUrl(e.target.value)}
              placeholder="https://yourapp.com"
            />
            <span className="field-hint">Used for Stripe webhooks, readiness checks, and deploy prep.</span>
          </label>
          <button type="submit" className="btn btn-primary" disabled={!!busy}>
            {busy === "save" ? "Saving…" : "Save settings"}
          </button>
        </form>
      </section>
    </div>
  );
}
