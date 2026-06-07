import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  healthApi,
  pipelineApi,
  projectsApi,
  vaultApi,
  type DiagnosticReport,
  type Project,
  type ReadinessResult,
  type VaultEntry,
  type VerificationResult,
} from "../api/client";
import DiagnosePanel from "../components/DiagnosePanel";
import PipelineTerminal from "../components/PipelineTerminal";
import ReadinessPanel from "../components/ReadinessPanel";
import ScoreRing from "../components/ScoreRing";
import VaultPanel from "../components/VaultPanel";
import { usePipelineWebSocket } from "../hooks/usePipelineWebSocket";

export default function ProjectPage() {
  const { slug = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [vaultEntries, setVaultEntries] = useState<VaultEntry[]>([]);
  const [vaultInitialized, setVaultInitialized] = useState(false);
  const [scanPath, setScanPath] = useState("");
  const [verifyResult, setVerifyResult] = useState<VerificationResult | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [syncEnv, setSyncEnv] = useState(false);
  const [forceOverwrite, setForceOverwrite] = useState(false);
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null);
  const [diagnoseReport, setDiagnoseReport] = useState<DiagnosticReport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [fixing, setFixing] = useState("");

  const { events, connected, clear } = usePipelineWebSocket(activeRunId);
  const pipelineRunning =
    activeRunId !== null &&
    events.length > 0 &&
    !events.some((e) => e.step === "run.completed" || e.step === "run.failed");

  const pipelineScore = useMemo(() => {
    const completed = events.find((e) => e.step === "run.completed");
    return completed?.score ?? null;
  }, [events]);

  async function load() {
    try {
      const p = await projectsApi.get(slug);
      setProject(p);
      setScanPath(p.local_path || "");
      const vault = await vaultApi.keys(slug);
      setVaultEntries(vault.entries);
      setVaultInitialized(vault.initialized);
      const scan = p.scan_data || {};
      if (typeof scan.lastHealthScore === "number" && !diagnoseReport) {
        setDiagnoseReport({
          scannedAt: String(scan.lastDiagnosedAt || ""),
          projectName: p.name,
          healthScore: scan.lastHealthScore as number,
          issues: [],
          summary: "Cached health score — run diagnose for details.",
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    }
  }

  useEffect(() => {
    load();
  }, [slug]);

  useEffect(() => {
    if (!activeRunId || pipelineRunning) return;
    const last = events[events.length - 1];
    if (last && (last.step === "run.completed" || last.step === "run.failed")) {
      load();
      runReadiness();
    }
  }, [events, activeRunId, pipelineRunning]);

  async function runScan() {
    setBusy("scan");
    setError("");
    try {
      setProject(await projectsApi.scan(slug, scanPath || undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setBusy("");
    }
  }

  async function runVerify() {
    setBusy("verify");
    setError("");
    try {
      setVerifyResult(await pipelineApi.verify(slug));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verify failed");
    } finally {
      setBusy("");
    }
  }

  async function runFullSetup() {
    setBusy("pipeline");
    setError("");
    clear();
    try {
      const run = await pipelineApi.start(slug, { sync_env: syncEnv, force: forceOverwrite });
      setActiveRunId(run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline start failed");
    } finally {
      setBusy("");
    }
  }

  async function runReadiness() {
    setBusy("readiness");
    try {
      setReadiness(await healthApi.readiness(slug));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Readiness failed");
    } finally {
      setBusy("");
    }
  }

  async function runDiagnose() {
    setBusy("diagnose");
    setError("");
    try {
      setDiagnoseReport(await healthApi.diagnose(slug));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Diagnose failed");
    } finally {
      setBusy("");
    }
  }

  async function runFix(opts: { all?: boolean; issue_ids?: string[]; action?: string }) {
    setFixing(opts.all ? "all" : opts.issue_ids?.[0] || opts.action || "fix");
    setError("");
    try {
      const result = await healthApi.fix(slug, { ...opts, force: forceOverwrite });
      setDiagnoseReport(result.report);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fix failed");
    } finally {
      setFixing("");
    }
  }

  async function downloadLastRun() {
    if (!activeRunId) return;
    setBusy("download");
    setError("");
    try {
      await pipelineApi.downloadRun(slug, activeRunId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setBusy("");
    }
  }

  async function downloadCodegenOnly() {
    setBusy("download");
    setError("");
    try {
      await pipelineApi.downloadCodegen(slug);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setBusy("");
    }
  }

  function handleVaultUpdate(entries: VaultEntry[], initialized: boolean) {
    setVaultEntries(entries);
    setVaultInitialized(initialized);
  }

  const pipelineComplete =
    activeRunId !== null && events.some((e) => e.step === "run.completed");

  const displayReadinessScore =
    pipelineScore ?? readiness?.score ?? project?.latest_readiness_score ?? null;

  if (!project) {
    return (
      <div className="page">
        <Link to="/" className="back-link">
          ← Projects
        </Link>
        <p className="muted">{error || "Loading…"}</p>
      </div>
    );
  }

  return (
    <div className="page">
      <Link to="/" className="back-link">
        ← Projects
      </Link>

      <div className="page-header">
        <div className="page-header-main">
          <h1>{project.name}</h1>
          <p className="muted">
            {project.framework} · {project.language}
            {project.last_scanned_at &&
              ` · scanned ${new Date(project.last_scanned_at).toLocaleString()}`}
          </p>
          <div className="score-pills">
            <ScoreRing score={displayReadinessScore} size={64} label="ready" />
            {diagnoseReport && (
              <ScoreRing score={diagnoseReport.healthScore} size={64} label="health" />
            )}
          </div>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary" onClick={runVerify} disabled={busy === "verify"}>
            {busy === "verify" ? "Verifying…" : "Verify keys"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={runReadiness}
            disabled={busy === "readiness"}
          >
            {busy === "readiness" ? "Checking…" : "Readiness"}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={runFullSetup}
            disabled={busy === "pipeline" || pipelineRunning}
          >
            {pipelineRunning ? "Running…" : "Run full setup"}
          </button>
          {pipelineComplete && activeRunId && (
            <button type="button" className="btn btn-secondary" onClick={downloadLastRun} disabled={busy === "download"}>
              Download zip
            </button>
          )}
          <button type="button" className="btn btn-secondary" onClick={downloadCodegenOnly} disabled={busy === "download"}>
            Codegen zip
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <section className="card pipeline-card">
        <div className="card-header-row">
          <h2>Live pipeline</h2>
          <span className="pipeline-hint">WebSocket · Django Channels + Celery</span>
        </div>
        <div className="option-row compact">
          <label className="toggle-inline">
            <input type="checkbox" checked={syncEnv} onChange={(e) => setSyncEnv(e.target.checked)} />
            Sync .env.local
          </label>
          <label className="toggle-inline">
            <input type="checkbox" checked={forceOverwrite} onChange={(e) => setForceOverwrite(e.target.checked)} />
            Overwrite files
          </label>
        </div>
        <PipelineTerminal
          events={
            events.length
              ? [{ step: "vault.unlock", status: "ok", message: "Vault unlocked" }, ...events]
              : []
          }
          connected={connected}
          running={pipelineRunning || busy === "pipeline"}
          emptyMessage="Click Run full setup — verify → provision → generate → readiness."
        />
      </section>

      <div className="grid-2">
        <ReadinessPanel
          score={displayReadinessScore}
          label={readiness?.label}
          checks={readiness?.checks || []}
          loading={busy === "readiness"}
        />
        <DiagnosePanel
          report={diagnoseReport}
          loading={busy === "diagnose"}
          fixing={fixing}
          onDiagnose={runDiagnose}
          onFixAll={() => runFix({ all: true })}
          onFixIssue={(id, action) => runFix({ issue_ids: [id], action: action || undefined })}
        />
      </div>

      {verifyResult && (
        <section className="card">
          <h2>Verification</h2>
          <pre className="verify-pre">
            {`Secret key      ${verifyResult.secretKey.valid ? "✓" : "✗"}  ${verifyResult.secretKey.message}
Publishable key ${verifyResult.publishableKey.valid ? "✓" : "✗"}  ${verifyResult.publishableKey.message}
${verifyResult.accountName ? `Account         ${verifyResult.accountName}` : ""}`}
          </pre>
        </section>
      )}

      <div className="grid-2">
        <section className="card">
          <h2>Scanner</h2>
          <label>
            Local path
            <input value={scanPath} onChange={(e) => setScanPath(e.target.value)} />
          </label>
          <button type="button" className="btn btn-primary" onClick={runScan} disabled={busy === "scan"}>
            {busy === "scan" ? "Scanning…" : "Run scan"}
          </button>
          {Array.isArray(project.scan_data?.recommendations) && (
            <ul className="rec-list">
              {(project.scan_data.recommendations as string[]).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </section>

        <VaultPanel
          projectSlug={slug}
          initialized={vaultInitialized}
          entries={vaultEntries}
          onUpdate={handleVaultUpdate}
          busy={busy}
          setBusy={setBusy}
          onError={setError}
        />
      </div>
    </div>
  );
}
