import { useEffect, useState } from "react";

import { deployApi, type Project } from "../api/client";

type Props = {
  projectSlug: string;
  project: Project;
  forceOverwrite: boolean;
  onError: (msg: string) => void;
  onGenerated: () => void;
};

export default function InfraPanel({ projectSlug, project, forceOverwrite, onError, onGenerated }: Props) {
  const [preview, setPreview] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const [lastWritten, setLastWritten] = useState<string[]>([]);
  const [pushMessage, setPushMessage] = useState("");

  const platform = String(
    (project.scan_data?.deployPlatform as string | undefined) || "detecting on scan"
  );

  async function loadPreview() {
    try {
      const data = await deployApi.infraPreview(projectSlug);
      setPreview(data.paths);
    } catch {
      setPreview([]);
    }
  }

  useEffect(() => {
    loadPreview();
  }, [projectSlug, project.updated_at]);

  async function generate() {
    setBusy("generate");
    onError("");
    try {
      const result = await deployApi.generateInfra(projectSlug, { force: forceOverwrite });
      setLastWritten(result.written.map((w) => w.path));
      onGenerated();
      await loadPreview();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Infra generation failed");
    } finally {
      setBusy("");
    }
  }

  async function pushDeploy() {
    setBusy("push");
    onError("");
    setPushMessage("");
    try {
      const result = await deployApi.deployPush(projectSlug);
      setPushMessage(result.message);
      if (!result.success) {
        onError(result.message);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Platform push failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="card">
      <h2>Deploy files</h2>
      <p className="muted">
        Generate Dockerfile, backup scripts, deploy guides, and platform config for{" "}
        <strong>{platform}</strong>.
      </p>
      <p className="muted vault-hint">
        Writes to project local path: db/schema.sql, deploy/*.md, scripts/backup-db.*, Dockerfile
      </p>
      <div className="option-row compact">
        <button type="button" className="btn btn-primary" onClick={generate} disabled={busy === "generate"}>
          {busy === "generate" ? "Generating…" : "Generate deploy files"}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={pushDeploy}
          disabled={busy === "push" || platform === "detecting on scan"}
          title="Runs vercel --prod or railway up in project directory"
        >
          {busy === "push" ? "Deploying…" : "Push to platform"}
        </button>
      </div>
      {preview.length > 0 && (
        <ul className="infra-file-list">
          {preview.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
      {lastWritten.length > 0 && (
        <p className="text-success">Wrote {lastWritten.length} file(s): {lastWritten.join(", ")}</p>
      )}
      {pushMessage && <p className={pushMessage.startsWith("Deployed") ? "text-success" : "muted"}>{pushMessage}</p>}
    </section>
  );
}
