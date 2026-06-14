import { useEffect, useState } from "react";

import { deployApi, type PostgresStatus, type Project } from "../api/client";

type Provider = "neon" | "supabase" | "railway" | "self-hosted";

type Props = {
  projectSlug: string;
  project: Project;
  onRefreshProject: () => void;
  onError: (msg: string) => void;
};

const PROVIDERS: { id: Provider; label: string; hint: string }[] = [
  { id: "neon", label: "Neon", hint: "NEON_API_KEY" },
  { id: "supabase", label: "Supabase", hint: "SUPABASE_ACCESS_TOKEN + ORG_ID" },
  { id: "railway", label: "Railway", hint: "RAILWAY_API_TOKEN" },
  { id: "self-hosted", label: "Self-hosted", hint: "DATABASE_URL in vault" },
];

export default function DatabasePanel({ projectSlug, project, onRefreshProject, onError }: Props) {
  const [status, setStatus] = useState<PostgresStatus | null>(null);
  const [schema, setSchema] = useState("");
  const [showSchema, setShowSchema] = useState(false);
  const [busy, setBusy] = useState("");

  async function loadStatus() {
    try {
      setStatus(await deployApi.postgresStatus(projectSlug));
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load database status");
    }
  }

  useEffect(() => {
    loadStatus();
  }, [projectSlug]);

  async function runProvision(provider: Provider) {
    setBusy(`provision-${provider}`);
    onError("");
    try {
      await deployApi.provisionPostgres(projectSlug, { provider, reuse: true, apply_schema: true });
      await loadStatus();
      onRefreshProject();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Provision failed");
    } finally {
      setBusy("");
    }
  }

  async function runTest() {
    setBusy("test");
    onError("");
    try {
      const result = await deployApi.testPostgres(projectSlug);
      await loadStatus();
      if (!result.ok) onError(result.message);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Connection test failed");
    } finally {
      setBusy("");
    }
  }

  async function runApplySchema() {
    setBusy("apply");
    onError("");
    try {
      const result = await deployApi.applySchema(projectSlug);
      await loadStatus();
      onRefreshProject();
      if (!result.ok) onError(result.message);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Schema apply failed");
    } finally {
      setBusy("");
    }
  }

  async function toggleSchema() {
    if (showSchema) {
      setShowSchema(false);
      return;
    }
    setBusy("schema");
    try {
      const data = await deployApi.postgresSchema(projectSlug);
      setSchema(data.schema);
      setShowSchema(true);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load schema");
    } finally {
      setBusy("");
    }
  }

  const postgresMeta = project.scan_data?.postgres as Record<string, unknown> | undefined;

  return (
    <section className="card">
      <h2>Database</h2>
      <p className="muted">
        {status?.configured ? "✓ DATABASE_URL in vault" : status?.message || "Provision or set DATABASE_URL in vault."}
      </p>
      {status?.connectionMessage && (
        <p className={status.connected ? "text-success" : "text-danger"}>{status.connectionMessage}</p>
      )}
      {status?.schemaApplied && <p className="text-success">✓ Schema applied</p>}
      {postgresMeta?.provider != null && (
        <p className="muted">Provider: {String(postgresMeta.provider)}</p>
      )}

      <div className="option-row compact db-providers">
        {PROVIDERS.map((p) => (
          <button
            key={p.id}
            type="button"
            className="btn btn-secondary btn-sm"
            title={p.hint}
            onClick={() => runProvision(p.id)}
            disabled={busy === `provision-${p.id}`}
          >
            {busy === `provision-${p.id}` ? "…" : p.label}
          </button>
        ))}
      </div>
      <div className="option-row compact">
        <button type="button" className="btn btn-secondary" onClick={runTest} disabled={busy === "test"}>
          {busy === "test" ? "…" : "Test connection"}
        </button>
        <button type="button" className="btn btn-secondary" onClick={runApplySchema} disabled={busy === "apply"}>
          {busy === "apply" ? "…" : "Apply schema"}
        </button>
        <button type="button" className="btn btn-ghost" onClick={toggleSchema} disabled={busy === "schema"}>
          {showSchema ? "Hide schema" : "View schema"}
        </button>
      </div>
      {showSchema && schema && <pre className="verify-pre schema-pre">{schema}</pre>}
    </section>
  );
}

