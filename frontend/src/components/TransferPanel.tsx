import { useCallback, useEffect, useState } from "react";

import {
  transferApi,
  type TransferDeployResult,
  type TransferImportResult,
  type TransferProviderStatus,
} from "../api/client";

type Props = {
  projectSlug: string;
  gitUrl?: string;
  projectName?: string;
  onError: (msg: string) => void;
};

type DeployRunRow = {
  deploymentId: string;
  appName: string;
  targetProvider: string;
  status: string;
  live: boolean;
  liveUrl?: string;
  createdAt?: string;
};

export default function TransferPanel({ projectSlug, gitUrl, projectName, onError }: Props) {
  const [providers, setProviders] = useState<TransferProviderStatus[]>([]);
  const [repoUrl, setRepoUrl] = useState(gitUrl || "");
  const [branch, setBranch] = useState("main");
  const [importResult, setImportResult] = useState<TransferImportResult | null>(null);

  const [appName, setAppName] = useState(projectName || "");
  const [targetProvider, setTargetProvider] = useState("railway");
  const [targetEnv, setTargetEnv] = useState("stage");
  const [filesText, setFilesText] = useState("package.json");
  const [enableStripe, setEnableStripe] = useState(false);
  const [enableMonitoring, setEnableMonitoring] = useState(true);
  const [enableBackups, setEnableBackups] = useState(true);
  const [deployResult, setDeployResult] = useState<TransferDeployResult | null>(null);
  const [history, setHistory] = useState<DeployRunRow[]>([]);

  const [railwayServiceId, setRailwayServiceId] = useState("");
  const [railwayServiceName, setRailwayServiceName] = useState("");
  const [backupMessage, setBackupMessage] = useState("");

  const [transferDryRun, setTransferDryRun] = useState(true);
  const [transferQueueOnly, setTransferQueueOnly] = useState(false);
  const [transferMode, setTransferMode] = useState("queue");
  const [transferOnly, setTransferOnly] = useState("");
  const [activeTransfer, setActiveTransfer] = useState<Record<string, unknown> | null>(null);
  const [transferRuns, setTransferRuns] = useState<Array<Record<string, unknown>>>([]);

  const [setupTasks, setSetupTasks] = useState<Array<Record<string, unknown>>>([]);
  const [setupSummary, setSetupSummary] = useState<Record<string, unknown> | null>(null);
  const [setupMessage, setSetupMessage] = useState("");

  const [busy, setBusy] = useState("");

  const loadProviders = useCallback(async () => {
    try {
      const data = await transferApi.providerStatus();
      setProviders(data.providers);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Provider status failed");
    }
  }, [onError]);

  const loadHistory = useCallback(async () => {
    try {
      const data = await transferApi.projectDeployHistory(projectSlug);
      setHistory(
        (data.runs || []).map((r) => ({
          deploymentId: String(r.deploymentId || ""),
          appName: String(r.appName || ""),
          targetProvider: String(r.targetProvider || ""),
          status: String(r.status || ""),
          live: Boolean(r.live),
          liveUrl: r.liveUrl ? String(r.liveUrl) : undefined,
          createdAt: r.createdAt ? String(r.createdAt) : undefined,
        }))
      );
    } catch {
      /* optional */
    }
  }, [projectSlug]);

  const loadTransferRuns = useCallback(async () => {
    try {
      const status = await transferApi.transferRunStatus();
      setActiveTransfer(status.run);
      const hist = await transferApi.transferRunHistory(projectSlug, 15);
      setTransferRuns(hist.runs || []);
    } catch {
      /* optional */
    }
  }, [projectSlug]);

  const loadPlatformSetup = useCallback(async () => {
    try {
      const data = await transferApi.platformSetupAudit();
      setSetupTasks(data.tasks || []);
      setSetupSummary(data.summary || null);
    } catch {
      /* optional */
    }
  }, []);

  useEffect(() => {
    setRepoUrl(gitUrl || "");
  }, [gitUrl]);

  useEffect(() => {
    loadProviders();
    loadHistory();
    loadTransferRuns();
    loadPlatformSetup();
  }, [loadProviders, loadHistory, loadTransferRuns, loadPlatformSetup]);

  async function runGithubImport() {
    setBusy("import");
    onError("");
    try {
      const data = (await transferApi.projectGithubImport(
        projectSlug,
        repoUrl || undefined,
        branch
      )) as TransferImportResult;
      setImportResult(data);
      if (data.project?.appName) setAppName(data.project.appName);
      if (data.project?.repoUrl) setRepoUrl(data.project.repoUrl);
      if (data.project?.branch) setBranch(data.project.branch);
      if (data.files?.length) setFilesText(data.files.slice(0, 80).join("\n"));
    } catch (e) {
      onError(e instanceof Error ? e.message : "GitHub import failed");
    } finally {
      setBusy("");
    }
  }

  async function runDeploy() {
    setBusy("deploy");
    onError("");
    setDeployResult(null);
    try {
      const files = filesText
        .split("\n")
        .map((f) => f.trim())
        .filter(Boolean);
      const { result } = await transferApi.projectDeploy(projectSlug, {
        appName,
        targetProvider,
        repoUrl,
        branch,
        targetEnvironment: targetEnv,
        files,
        packageJson: importResult?.packageJson || undefined,
        environment: {},
        secrets: [],
        enableStripe,
        enableMonitoring,
        enableBackups,
      });
      setDeployResult(result as TransferDeployResult);
      await loadHistory();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Deploy failed");
    } finally {
      setBusy("");
    }
  }

  async function runTransferMigration() {
    setBusy("transfer");
    onError("");
    try {
      const only = transferOnly
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const { run } = await transferApi.transferStart(
        {
          mode: transferMode,
          only: transferMode === "demand" ? only : only.length ? only : undefined,
          dryRun: transferDryRun,
          queueOnly: transferQueueOnly,
        },
        projectSlug
      );
      setActiveTransfer(run);
      await loadTransferRuns();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Transfer start failed");
    } finally {
      setBusy("");
    }
  }

  async function stopTransfer() {
    setBusy("transfer-stop");
    onError("");
    try {
      const data = await transferApi.transferStop();
      setActiveTransfer(data.run);
      await loadTransferRuns();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Transfer stop failed");
    } finally {
      setBusy("");
    }
  }

  async function replayTransfer(runId: string) {
    setBusy(`replay-${runId}`);
    onError("");
    try {
      await transferApi.transferReplay(runId);
      await loadTransferRuns();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Replay failed");
    } finally {
      setBusy("");
    }
  }

  async function runSetupAction(actionId: string) {
    setBusy(`setup-${actionId}`);
    onError("");
    setSetupMessage("");
    try {
      const result = await transferApi.platformSetupRun(actionId);
      setSetupMessage(String(result.message || "Done"));
      await loadPlatformSetup();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Setup action failed");
    } finally {
      setBusy("");
    }
  }

  async function refreshStatus(deploymentId: string) {
    setBusy(`status-${deploymentId}`);
    onError("");
    try {
      await transferApi.refreshDeployStatus(projectSlug, deploymentId);
      await loadHistory();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Status refresh failed");
    } finally {
      setBusy("");
    }
  }

  async function runRailwayBackup() {
    setBusy("backup");
    onError("");
    setBackupMessage("");
    try {
      const data = await transferApi.railwayEnvBackup(
        railwayServiceId,
        railwayServiceName || undefined,
        true
      );
      setBackupMessage(String(data.message || "Backup complete"));
    } catch (e) {
      onError(e instanceof Error ? e.message : "Railway backup failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <section className="card">
        <h2>Render → Railway migration</h2>
        <p className="muted">
          Lists Render services (needs <code>RENDER_API_TOKEN</code>) and creates matching Railway services. Nothing
          runs until you click Start. <strong>Dry run</strong> is on by default — preview only, no Railway changes.
        </p>
        <div className="option-row">
          <label>
            Mode
            <select value={transferMode} onChange={(e) => setTransferMode(e.target.value)}>
              <option value="queue">queue (all services)</option>
              <option value="demand">demand (specific services)</option>
            </select>
          </label>
          <label>
            Service names / IDs (demand mode)
            <input
              value={transferOnly}
              onChange={(e) => setTransferOnly(e.target.value)}
              placeholder="my-app or srv-xxx"
            />
          </label>
        </div>
        <div className="option-row">
          <label className="inline">
            <input type="checkbox" checked={transferDryRun} onChange={(e) => setTransferDryRun(e.target.checked)} />
            Dry run (no Railway writes)
          </label>
          <label className="inline">
            <input
              type="checkbox"
              checked={transferQueueOnly}
              onChange={(e) => setTransferQueueOnly(e.target.checked)}
            />
            Queue only (do not spawn worker)
          </label>
        </div>
        <div className="option-row">
          <button
            type="button"
            className="btn btn-primary"
            onClick={runTransferMigration}
            disabled={busy === "transfer"}
          >
            {busy === "transfer" ? "Starting…" : "Start migration"}
          </button>
          <button
            type="button"
            className="btn btn-outline"
            onClick={stopTransfer}
            disabled={busy === "transfer-stop"}
          >
            Stop active run
          </button>
          <button type="button" className="btn btn-outline btn-sm" onClick={loadTransferRuns}>
            Refresh status
          </button>
        </div>
        {activeTransfer && (
          <div className="deploy-live">
            <p>
              Active: <strong>{String(activeTransfer.id || "—")}</strong>{" "}
              <span className={`badge ${activeTransfer.running ? "badge-warn" : "badge-ok"}`}>
                {String(activeTransfer.status || "idle")}
              </span>
            </p>
            {activeTransfer.logTail ? (
              <pre className="verify-pre">{String(activeTransfer.logTail)}</pre>
            ) : null}
          </div>
        )}
        {transferRuns.length > 0 && (
          <table className="members-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Step</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {transferRuns.map((run) => {
                const id = String(run.id || "");
                return (
                  <tr key={id}>
                    <td>{id.slice(0, 8)}…</td>
                    <td>{String(run.status)}</td>
                    <td>{String(run.step)}</td>
                    <td>
                      {["failed", "stopped", "dead_letter"].includes(String(run.status)) && (
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          disabled={busy === `replay-${id}`}
                          onClick={() => replayTransfer(id)}
                        >
                          Replay
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Platform setup</h2>
        <p className="muted">
          Audit local credentials (<code>private_env/</code> + vault). Verify actions are read-only API checks — they
          do not push env vars to Render or Railway.
        </p>
        {setupSummary && (
          <p>
            {Number(setupSummary.readyCount || 0)} ready · {Number(setupSummary.needsAttention || 0)} need attention
          </p>
        )}
        <button type="button" className="btn btn-outline btn-sm" onClick={loadPlatformSetup}>
          Refresh audit
        </button>
        <button
          type="button"
          className="btn btn-outline btn-sm"
          onClick={() => runSetupAction("verify_all_providers")}
          disabled={busy === "setup-verify_all_providers"}
        >
          Verify all
        </button>
        {setupMessage && <p className="success-msg">{setupMessage}</p>}
        <ul className="provider-list">
          {setupTasks.map((task) => (
            <li key={String(task.id)}>
              <strong>{String(task.service)}</strong>
              <span className={`badge ${task.status === "ready" ? "badge-ok" : "badge-warn"}`}>
                {String(task.status)}
              </span>
              {(task.autoActions as Array<{ id: string; label: string }> | undefined)?.map((action) => (
                <button
                  key={action.id}
                  type="button"
                  className="btn btn-outline btn-sm"
                  disabled={busy === `setup-${action.id}`}
                  onClick={() => runSetupAction(action.id)}
                >
                  {action.label}
                </button>
              ))}
            </li>
          ))}
        </ul>
        <p className="muted">
          Queued migrations: run <code>npm run transfer:worker</code> in a second terminal (processes{" "}
          <code>queueOnly</code> jobs).
        </p>
      </section>

      <section className="card">
        <h2>API Transfer — provider readiness</h2>
        <p className="muted">
          Live deploy uses platform tokens from <code>private_env/</code> or project vault keys.
        </p>
        <ul className="provider-list">
          {providers.map((p) => (
            <li key={p.provider}>
              <strong>{p.provider}</strong>
              <span className={`badge ${p.liveEnabled ? "badge-ok" : "badge-warn"}`}>{p.status}</span>
            </li>
          ))}
        </ul>
        <button type="button" className="btn btn-outline btn-sm" onClick={loadProviders}>
          Refresh
        </button>
      </section>

      <section className="card">
        <h2>GitHub import</h2>
        <p className="muted">Detect framework and file tree from a repo (uses vault GITHUB_TOKEN for private repos).</p>
        <div className="option-row">
          <label>
            Repository URL
            <input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/org/repo" />
          </label>
          <label>
            Branch
            <input value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" />
          </label>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={runGithubImport}
          disabled={busy === "import" || !repoUrl.trim()}
        >
          {busy === "import" ? "Importing…" : "Import from GitHub"}
        </button>
        {importResult?.repository && (
          <p className="success-msg">
            {importResult.repository.fullName} @ {importResult.repository.branch}
            {importResult.framework && (
              <> — {importResult.framework.framework} ({importResult.framework.confidence}%)</>
            )}
          </p>
        )}
      </section>

      <section className="card">
        <h2>One-click deploy (Railway / Render / Fly)</h2>
        <p className="muted">
          Full API Transfer pipeline — vault secrets are merged server-side. Simulated stages run when tokens are missing.
        </p>
        <div className="option-row">
          <label>
            App name
            <input value={appName} onChange={(e) => setAppName(e.target.value)} />
          </label>
          <label>
            Provider
            <select value={targetProvider} onChange={(e) => setTargetProvider(e.target.value)}>
              <option value="railway">railway</option>
              <option value="render">render</option>
              <option value="fly">fly</option>
            </select>
          </label>
          <label>
            Environment
            <select value={targetEnv} onChange={(e) => setTargetEnv(e.target.value)}>
              <option value="dev">dev</option>
              <option value="stage">stage</option>
              <option value="prod">prod</option>
            </select>
          </label>
        </div>
        <label className="block-label">
          Project files (one path per line)
          <textarea rows={4} value={filesText} onChange={(e) => setFilesText(e.target.value)} />
        </label>
        <div className="option-row">
          <label className="inline">
            <input type="checkbox" checked={enableStripe} onChange={(e) => setEnableStripe(e.target.checked)} />
            Stripe stage
          </label>
          <label className="inline">
            <input type="checkbox" checked={enableMonitoring} onChange={(e) => setEnableMonitoring(e.target.checked)} />
            Monitoring
          </label>
          <label className="inline">
            <input type="checkbox" checked={enableBackups} onChange={(e) => setEnableBackups(e.target.checked)} />
            Backups
          </label>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={runDeploy}
          disabled={busy === "deploy" || !appName.trim()}
        >
          {busy === "deploy" ? "Deploying…" : "Run deploy pipeline"}
        </button>
        {deployResult && (
          <div className="deploy-live">
            <p>
              Status:{" "}
              <span className={`badge ${deployResult.succeeded ? "badge-ok" : "badge-warn"}`}>
                {deployResult.succeeded ? "Succeeded" : "Needs attention"}
              </span>
            </p>
            {deployResult.liveExecution && (
              <p className="muted">{deployResult.liveExecution.message}</p>
            )}
            {deployResult.liveUrl && (
              <p>
                <a href={deployResult.liveUrl} target="_blank" rel="noopener noreferrer">
                  {deployResult.liveUrl}
                </a>
              </p>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Deployment history</h2>
        {history.length === 0 ? (
          <p className="muted">No transfer deploy runs yet.</p>
        ) : (
          <table className="members-table">
            <thead>
              <tr>
                <th>App</th>
                <th>Provider</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {history.map((run) => (
                <tr key={run.deploymentId}>
                  <td>{run.appName}</td>
                  <td>{run.targetProvider}</td>
                  <td>
                    <span className={`badge ${run.status === "live" ? "badge-ok" : "badge-warn"}`}>
                      {run.status}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-outline btn-sm"
                      disabled={busy === `status-${run.deploymentId}`}
                      onClick={() => refreshStatus(run.deploymentId)}
                    >
                      Refresh
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Railway env backup</h2>
        <p className="muted">Snapshot all variables on a Railway service (server-side; keys only in response).</p>
        <div className="option-row">
          <label>
            Service ID
            <input
              value={railwayServiceId}
              onChange={(e) => setRailwayServiceId(e.target.value)}
              placeholder="Railway service UUID"
            />
          </label>
          <label>
            Service name (optional)
            <input value={railwayServiceName} onChange={(e) => setRailwayServiceName(e.target.value)} />
          </label>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={runRailwayBackup}
          disabled={busy === "backup" || !railwayServiceId.trim()}
        >
          {busy === "backup" ? "Backing up…" : "Backup Railway env"}
        </button>
        {backupMessage && <p className="success-msg">{backupMessage}</p>}
      </section>
    </>
  );
}
