import { useCallback, useEffect, useState } from "react";

import { pipelineApi, type DeployRunResult, type PipelineRun } from "../api/client";

type Props = {
  projectSlug: string;
  activeRunId: string | null;
  onSelectRun: (runId: string) => void;
  onNextSteps?: (steps: string[]) => void;
};

function runLabel(run: PipelineRun): string {
  if (run.options?.mode === "deploy") return "deploy";
  return "setup";
}

export default function RunsPanel({ projectSlug, activeRunId, onSelectRun, onNextSteps }: Props) {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRuns(await pipelineApi.list(projectSlug));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }, [projectSlug]);

  useEffect(() => {
    load();
  }, [load, activeRunId]);

  async function selectRun(runId: string) {
    onSelectRun(runId);
    if (!onNextSteps) return;
    try {
      const run = await pipelineApi.get(projectSlug, runId);
      const deploy = run.result?.deploy as DeployRunResult | undefined;
      onNextSteps(deploy?.nextSteps || []);
    } catch {
      onNextSteps([]);
    }
  }

  async function downloadRun(runId: string) {
    setBusy(runId);
    setError("");
    try {
      await pipelineApi.downloadRun(projectSlug, runId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="card">
      <div className="card-header-row">
        <h2>Pipeline runs</h2>
        <button type="button" className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      {loading && runs.length === 0 ? (
        <p className="muted">Loading…</p>
      ) : runs.length === 0 ? (
        <p className="muted">No runs yet — start a pipeline above.</p>
      ) : (
        <ul className="runs-list">
          {runs.map((run) => (
            <li key={run.id} className={activeRunId === run.id ? "runs-item active" : "runs-item"}>
              <button type="button" className="runs-item-main" onClick={() => selectRun(run.id)}>
                <span className={`run-pill run-${run.status}`}>{run.status}</span>
                <span className="run-pill run-type">{runLabel(run)}</span>
                <span className="runs-item-meta">
                  {new Date(run.created_at).toLocaleString()}
                  {run.readiness_score != null && ` · readiness ${run.readiness_score}`}
                </span>
              </button>
              {run.status === "completed" && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busy === run.id}
                  onClick={() => downloadRun(run.id)}
                >
                  {busy === run.id ? "…" : "Zip"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
