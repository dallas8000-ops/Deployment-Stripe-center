import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  aiApi,
  deployApi,
  healthApi,
  pipelineApi,
  projectsApi,
  vaultApi,
  type DiagnosticReport,
  type HandoffPack,
  type Project,
  type ReadinessResult,
  type VaultEntry,
  type VerificationResult,
  type DeployRunResult,
} from "../api/client";
import AiCopilotPanel from "../components/AiCopilotPanel";
import CiGatePanel from "../components/CiGatePanel";
import DatabasePanel from "../components/DatabasePanel";
import MonitoringPanel from "../components/MonitoringPanel";
import DeployConfigPanel from "../components/DeployConfigPanel";
import DeployNextSteps from "../components/DeployNextSteps";
import DiagnosePanel from "../components/DiagnosePanel";
import InfraPanel from "../components/InfraPanel";
import PipelineCompleteCard, { type CompletionData } from "../components/PipelineCompleteCard";
import PipelineTerminal from "../components/PipelineTerminal";
import ReadinessPanel from "../components/ReadinessPanel";
import RunsPanel from "../components/RunsPanel";
import ScoreRing from "../components/ScoreRing";
import StripeConfigPanel from "../components/StripeConfigPanel";
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
  const [provisionPostgres, setProvisionPostgres] = useState(true);
  const [pushPlatform, setPushPlatform] = useState(false);
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null);
  const [diagnoseReport, setDiagnoseReport] = useState<DiagnosticReport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [fixing, setFixing] = useState("");
  const [nextSteps, setNextSteps] = useState<string[]>([]);
  const [completionData, setCompletionData] = useState<CompletionData | null>(null);

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
      if (typeof scan.lastHealthScore === "number" && scan.lastHealthScore > 0 && !diagnoseReport) {
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
      pipelineApi.get(slug, activeRunId).then((run) => {
        const deploy = run.result?.deploy as DeployRunResult | undefined;
        setNextSteps(deploy?.nextSteps || []);
        if (last.step === "run.completed") {
          const result = run.result || {};
          const provision = result.provision as Record<string, unknown> | undefined;
          const filesRaw = result.files_written ?? result.filesWritten;
          const files = Array.isArray(filesRaw)
            ? (filesRaw as string[]).map((f) => f.split("/").pop() ?? f).filter(Boolean)
            : [];
          setCompletionData({
            score: run.readiness_score,
            filesGenerated: files,
            productsProvisioned: typeof provision?.products === "number" ? provision.products : 0,
            pricesProvisioned: typeof provision?.prices === "number" ? provision.prices : 0,
            webhookRegistered: provision?.webhook === true,
            nextSteps: deploy?.nextSteps || [],
          });
        }
      }).catch(() => setNextSteps([]));
    }
  }, [events, activeRunId, pipelineRunning]);

  async function runOpenPr(handoff?: HandoffPack) {
    setBusy("open-pr");
    setError("");
    try {
      let title: string | undefined;
      let body: string | undefined;
      if (handoff) {
        title = `Stripe Installer setup — ${project?.name || slug}`;
        body = `${handoff.prDescription}\n\n---\n\n## Test checklist\n\n${handoff.testChecklist}\n\n---\n\n## Ops runbook\n\n${handoff.opsRunbook}`;
      } else {
        try {
          const pack = await aiApi.handoffPack(slug);
          title = `Stripe Installer setup — ${project?.name || slug}`;
          body = `${pack.prDescription}\n\n---\n\n## Test checklist\n\n${pack.testChecklist}`;
        } catch {
          /* open PR with default body if handoff fails */
        }
      }
      const result = await projectsApi.openPr(slug, { title, body });
      window.open(result.url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Open PR failed");
    } finally {
      setBusy("");
    }
  }

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
    setNextSteps([]);
    setCompletionData(null);
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

  async function runDeploy() {
    setBusy("deploy");
    setError("");
    clear();
    setNextSteps([]);
    try {
      const run = await deployApi.deployRun(slug, {
        sync_env: syncEnv,
        force: forceOverwrite,
        provision: true,
        generate: true,
        include_infra: true,
        provision_postgres: provisionPostgres,
        push: pushPlatform,
      });
      setActiveRunId(run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Deploy start failed");
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

  const [envPushServiceId, setEnvPushServiceId] = useState("");
  const [envPushProjectId, setEnvPushProjectId] = useState("");
  const [envPushResult, setEnvPushResult] = useState<string | null>(null);

  async function runEnvPush() {
    setBusy("env-push");
    setError("");
    setEnvPushResult(null);
    try {
      const result = await deployApi.pushEnvToPlatform(slug, {
        platform: "railway",
        service_id: envPushServiceId,
        project_id: envPushProjectId || undefined,
      });
      setEnvPushResult(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Env push failed");
    } finally {
      setBusy("");
    }
  }

  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!moreOpen) return;
    function handleClick(e: MouseEvent) {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [moreOpen]);

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
        <div className="page-header-main">
          <h1>{project.name}</h1>
          <p className="muted">
            {project.framework} · {project.language}
            {project.last_scanned_at &&
              ` · scanned ${new Date(project.last_scanned_at).toLocaleString()}`}
            {project.active_environment && project.active_environment !== "production" &&
              ` · env: ${project.active_environment}`}
          </p>
          <div className="env-selector">
            <label className="env-select-label">
              Active environment
              <select
                value={project.active_environment || "production"}
                onChange={async (e) => {
                  const active_environment = e.target.value as "test" | "staging" | "production";
                  try {
                    setProject(await projectsApi.update(slug, { active_environment }));
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "Failed to set environment");
                  }
                }}
              >
                <option value="test">Test</option>
                <option value="staging">Staging</option>
                <option value="production">Production</option>
              </select>
            </label>
          </div>
          <div className="score-pills">
            <ScoreRing score={displayReadinessScore} size={64} label="ready" />
            {diagnoseReport && (
              <ScoreRing score={diagnoseReport.healthScore} size={64} label="health" />
            )}
          </div>
        </div>
        <div className="page-actions">
          {/* Step-indicator: primary flow */}
          <div className="action-flow">
            <button type="button" className="btn btn-secondary btn-flow" onClick={runVerify} disabled={busy === "verify"}>
              {busy === "verify" ? "Verifying…" : "① Verify keys"}
            </button>
            <span className="flow-arrow">→</span>
            <button
              type="button"
              className="btn btn-secondary btn-flow"
              onClick={runReadiness}
              disabled={busy === "readiness"}
            >
              {busy === "readiness" ? "Checking…" : "② Readiness"}
            </button>
            <span className="flow-arrow">→</span>
            <button
              type="button"
              className="btn btn-primary btn-flow"
              onClick={runFullSetup}
              disabled={busy === "pipeline" || pipelineRunning}
            >
              {pipelineRunning ? "Running…" : "③ Run full setup"}
            </button>
          </div>

          {/* Secondary actions in overflow menu */}
          <div className="more-menu-wrapper" ref={moreRef}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setMoreOpen((v) => !v)}
              aria-label="More actions"
            >
              ···
            </button>
            {moreOpen && (
              <div className="more-menu">
                <button
                  type="button"
                  className="more-menu-item"
                  onClick={() => { runDeploy(); setMoreOpen(false); }}
                  disabled={busy === "deploy" || pipelineRunning}
                >
                  Deploy prep
                </button>
                {pipelineComplete && activeRunId && (
                  <button
                    type="button"
                    className="more-menu-item"
                    onClick={() => { downloadLastRun(); setMoreOpen(false); }}
                    disabled={busy === "download"}
                  >
                    Download zip
                  </button>
                )}
                <button
                  type="button"
                  className="more-menu-item"
                  onClick={() => { void runOpenPr(); setMoreOpen(false); }}
                  disabled={busy === "open-pr" || !project.local_path}
                  title="Requires GITHUB_TOKEN in vault and uncommitted generated files"
                >
                  Open GitHub PR
                </button>
                <button
                  type="button"
                  className="more-menu-item"
                  onClick={() => { downloadCodegenOnly(); setMoreOpen(false); }}
                  disabled={busy === "download"}
                >
                  Codegen zip
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {project.org_billing?.needsUpgrade && (
        <div className="alert">
          Organization <strong>{project.organization_name}</strong> is on the free tier (
          {project.org_billing.projectCount}/{project.org_billing.freeProjectLimit} projects).{" "}
          <Link to="/billing">Upgrade org billing</Link> for unlimited agency pipelines and members.
        </div>
      )}

      {/* ──────────────────────────────────────────── SECTION: SETUP ──────────────────────────────────────────── */}
      <div className="section-header">
        <h2>Setup</h2>
        <p className="muted">Secure keys and code scanning</p>
      </div>

      <div className="grid-2">
        <VaultPanel
          projectSlug={slug}
          initialized={vaultInitialized}
          entries={vaultEntries}
          onUpdate={handleVaultUpdate}
          busy={busy}
          setBusy={setBusy}
          onError={setError}
        />

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
      </div>

      {/* ──────────────────────────────────────────── SECTION: PIPELINE & HISTORY ──────────────────────────────────────────── */}
      <div className="section-header">
        <h2>Pipeline & History</h2>
        <p className="muted">Live events, runs, and next steps</p>
      </div>

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
          <label className="toggle-inline">
            <input
              type="checkbox"
              checked={provisionPostgres}
              onChange={(e) => setProvisionPostgres(e.target.checked)}
            />
            Provision Postgres
          </label>
          <label className="toggle-inline" title="Requires Vercel/Railway CLI installed and logged in">
            <input type="checkbox" checked={pushPlatform} onChange={(e) => setPushPlatform(e.target.checked)} />
            Push to platform
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

      <RunsPanel
        projectSlug={slug}
        activeRunId={activeRunId}
        onSelectRun={(runId) => {
          clear();
          setActiveRunId(runId);
        }}
        onNextSteps={setNextSteps}
      />

      <DeployNextSteps steps={nextSteps} />

      {completionData && pipelineComplete && (
        <PipelineCompleteCard
          data={completionData}
          runId={activeRunId}
          hasLocalPath={!!project.local_path}
          onOpenPr={runOpenPr}
          onDownload={downloadLastRun}
          downloading={busy === "download"}
          openingPr={busy === "open-pr"}
        />
      )}

      {/* ──────────────────────────────────────────── SECTION: HEALTH & READINESS ──────────────────────────────────────────── */}
      <div className="section-header">
        <h2>Health & Readiness</h2>
        <p className="muted">Diagnostics and readiness checks</p>
      </div>

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

      {/* ──────────────────────────────────────────── SECTION: CONFIGURATION ──────────────────────────────────────────── */}
      <div className="section-header">
        <h2>Configuration</h2>
        <p className="muted">Stripe, deployment, and CI settings</p>
      </div>

      <div className="grid-2">
        <StripeConfigPanel projectSlug={slug} hasLocalPath={!!project.local_path} onError={setError} />
        <DeployConfigPanel
          projectSlug={slug}
          hasLocalPath={!!project.local_path}
          onSaved={load}
          onError={setError}
        />
      </div>

      <CiGatePanel projectSlug={slug} hasGitUrl={!!project.git_url} onError={setError} />

      {/* ──────────────────────────────────────────── SECTION: GENERATION & DEPLOYMENT ──────────────────────────────────────────── */}
      <div className="section-header">
        <h2>Generation & Deployment</h2>
        <p className="muted">Database, infrastructure, and codegen</p>
      </div>

      <div className="grid-2">
        <DatabasePanel
          projectSlug={slug}
          project={project}
          onRefreshProject={load}
          onError={setError}
        />

        <InfraPanel
          projectSlug={slug}
          project={project}
          forceOverwrite={forceOverwrite}
          onError={setError}
          onGenerated={load}
        />
      </div>

      <section className="card">
        <h2>Push env vars to Railway</h2>
        <p className="muted">
          Send vault secrets (Stripe keys, webhook secret, DATABASE_URL) directly to your deployed
          Railway service — no manual copy-paste into the dashboard.
        </p>
        <div className="option-row">
          <label>
            Service ID
            <input
              placeholder="Railway service UUID"
              value={envPushServiceId}
              onChange={(e) => setEnvPushServiceId(e.target.value)}
            />
          </label>
          <label>
            Project ID
            <input
              placeholder="Railway project UUID"
              value={envPushProjectId}
              onChange={(e) => setEnvPushProjectId(e.target.value)}
            />
          </label>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={runEnvPush}
          disabled={busy === "env-push" || !envPushServiceId}
        >
          {busy === "env-push" ? "Pushing…" : "Push env vars"}
        </button>
        {envPushResult && <p className="success-msg">{envPushResult}</p>}
      </section>

      {/* ──────────────────────────────────────────── SECTION: MONITORING & AI ──────────────────────────────────────────── */}
      <div className="section-header">
        <h2>Monitoring & AI</h2>
        <p className="muted">Drift detection, audit logs, and intelligent suggestions</p>
      </div>

      <div className="grid-2">
        <AiCopilotPanel
          projectSlug={slug}
          diagnoseReport={diagnoseReport}
          readinessChecks={readiness?.checks || []}
          onError={setError}
          onFixIssue={(id, action) => runFix({ issue_ids: [id], action: action || undefined })}
          onApplyNlConfig={load}
          onConfigApplied={runDeploy}
          onCatalogApplied={() => runFix({ action: "provision-stripe" })}
          onOpenPrWithHandoff={(handoff) => runOpenPr(handoff)}
          fixing={fixing}
        />
        <MonitoringPanel
          projectSlug={slug}
          lastDrift={
            (project.scan_data?.lastDrift as {
              driftCount: number;
              checkedAt?: string;
              items?: { category: string; severity: string; message: string; fix: string }[];
            }) || null
          }
          onResynced={load}
        />
      </div>
    </div>
  );
}
