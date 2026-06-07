const api = window.stripeInstaller;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const VIEW_TITLES = {
  dashboard: "Dashboard",
  diagnose: "Diagnose & Fix",
  vault: "Secure Vault",
  stripe: "Stripe Setup",
  deploy: "Deploy",
  readiness: "Readiness",
};

const METRIC_ICONS = {
  framework: { icon: "⚙️", cls: "purple" },
  stripe: { icon: "💳", cls: "green" },
  platform: { icon: "☁️", cls: "purple" },
  manifest: { icon: "📋", cls: "amber" },
  vault: { icon: "🔐", cls: "green" },
  secrets: { icon: "⚠️", cls: "red" },
};

const els = {
  projectPath: $("#project-path"),
  vaultBadge: $("#vault-badge"),
  vaultDot: $("#vault-dot"),
  btnLock: $("#btn-lock"),
  activityLog: $("#activity-log"),
  activityPanel: $(".activity-panel"),
  dashboardContent: $("#dashboard-content"),
  dashboardEmpty: $("#dashboard-empty"),
  dashboardRecs: $("#dashboard-recs"),
  vaultLockedPanel: $("#vault-locked-panel"),
  vaultUnlockedPanel: $("#vault-unlocked-panel"),
  vaultKeys: $("#vault-keys"),
  stripeResult: $("#stripe-result"),
  deployResult: $("#deploy-result"),
  readinessResult: $("#readiness-result"),
  readinessScore: $("#readiness-score"),
  readinessScoreValue: $("#readiness-score-value"),
  scoreFill: $("#score-fill"),
  scoreTitle: $("#score-title"),
  scoreDesc: $("#score-desc"),
  breadcrumb: $("#page-breadcrumb"),
  diagnoseHero: $("#diagnose-hero"),
  diagnoseEmpty: $("#diagnose-empty"),
  diagnoseIssues: $("#diagnose-issues"),
  healthScore: $("#health-score"),
  healthBadge: $("#health-badge"),
  diagnoseSummary: $("#diagnose-summary"),
  diagnoseStats: $("#diagnose-stats"),
};

let vaultUnlocked = false;
let hasProject = false;

const SCORE_CIRCUMFERENCE = 327;

function log(message, type = "") {
  const line = document.createElement("div");
  line.className = `log-line ${type}`;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  els.activityLog.prepend(line);
  while (els.activityLog.children.length > 80) {
    els.activityLog.lastChild.remove();
  }
}

async function call(fn, ...args) {
  const result = await fn(...args);
  if (!result?.ok) throw new Error(result?.error ?? "Request failed");
  return result.data;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function setOutput(el, text) {
  if (!text) {
    el.innerHTML = `<span class="output-placeholder">${el.dataset.placeholder ?? "No output yet."}</span>`;
    return;
  }
  el.textContent = text;
}

function setVaultUi(unlocked, keys = []) {
  vaultUnlocked = unlocked;
  els.vaultBadge.textContent = unlocked ? "Vault unlocked" : "Vault locked";
  els.vaultDot.classList.toggle("unlocked", unlocked);
  els.btnLock.hidden = !unlocked;
  els.vaultLockedPanel.hidden = unlocked;
  els.vaultUnlockedPanel.hidden = !unlocked;
  els.vaultKeys.innerHTML = keys.map((k) => `<li>${escapeHtml(k)}</li>`).join("");
}

function setProjectUi(path) {
  hasProject = Boolean(path && path !== "No project selected");
  els.projectPath.textContent = path || "No project selected";
  els.projectPath.title = path || "";
  els.dashboardEmpty.hidden = hasProject;
  els.dashboardContent.hidden = !hasProject;
  if (!hasProject) {
    els.dashboardRecs.hidden = true;
    els.dashboardContent.innerHTML = "";
  }
}

function requireProject() {
  if (!hasProject) throw new Error("Select a project folder first");
  return els.projectPath.textContent;
}

function requireVault() {
  if (!vaultUnlocked) throw new Error("Unlock the vault first");
}

function metricCard(key, label, value, detail, pill) {
  const m = METRIC_ICONS[key] ?? { icon: "📊", cls: "purple" };
  const pillHtml = pill ? `<span class="pill pill-${pill.type}">${escapeHtml(pill.text)}</span>` : "";
  return `
    <div class="metric-card">
      <div class="metric-top">
        <div class="metric-icon ${m.cls}">${m.icon}</div>
        ${pillHtml}
      </div>
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value)}</div>
      <div class="metric-detail">${escapeHtml(detail)}</div>
    </div>`;
}

function updateScoreRing(score) {
  const offset = SCORE_CIRCUMFERENCE - (score / 100) * SCORE_CIRCUMFERENCE;
  els.scoreFill.style.strokeDashoffset = String(offset);

  let color = "#f87171";
  if (score >= 80) color = "#34d399";
  else if (score >= 50) color = "#fbbf24";
  els.scoreFill.style.stroke = color;

  if (score >= 80) {
    els.scoreTitle.textContent = "Production ready";
    els.scoreDesc.textContent = "Your project meets the readiness threshold for launch.";
  } else if (score >= 50) {
    els.scoreTitle.textContent = "Almost there";
    els.scoreDesc.textContent = "Address warnings below before going live.";
  } else {
    els.scoreTitle.textContent = "Needs work";
    els.scoreDesc.textContent = "Fix critical failures before deploying to production.";
  }
}

async function refreshVaultKeys() {
  if (!vaultUnlocked) return;
  const keys = await call(api.vaultListKeys);
  setVaultUi(true, keys);
}

async function selectProject() {
  const path = await call(api.selectProject);
  if (!path) return;
  setProjectUi(path);
  setVaultUi(false, []);
  log(`Opened project: ${path.split(/[/\\]/).pop()}`, "success");
  await refreshStatus();
}

function renderDashboard(status) {
  const p = status.profile;
  const secretsPill = p.detectedSecrets.length === 0
    ? { type: "success", text: "Clean" }
    : { type: "danger", text: `${p.detectedSecrets.length} found` };

  els.dashboardContent.innerHTML = [
    metricCard("framework", "Framework", p.framework, `${p.language}${p.nextRouter ? ` · ${p.nextRouter}` : ""}`),
    metricCard("stripe", "Stripe integration", p.existingStripeCode ? "Detected" : "Not found", p.suggestedFeatures.join(", ") || "No features suggested"),
    metricCard("platform", "Deploy target", status.platform, "Auto-detected hosting platform"),
    metricCard("manifest", "Price catalog", String(status.manifest?.prices?.length ?? 0), status.manifest ? `Updated ${status.manifest.updatedAt.slice(0, 10)}` : "Run pipeline to provision"),
    metricCard("vault", "Vault keys", String(status.vaultKeys.length), status.vaultKeys.slice(0, 3).join(", ") || "No keys stored"),
    metricCard("secrets", "File secrets", String(p.detectedSecrets.length), "Move to encrypted vault", secretsPill),
  ].join("");

  if (p.recommendations?.length) {
    els.dashboardRecs.hidden = false;
    els.dashboardRecs.innerHTML = `
      <h2 class="subsection-title">Recommendations</h2>
      <ul class="rec-list">${p.recommendations.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>`;
  } else {
    els.dashboardRecs.hidden = true;
  }
}

async function refreshStatus() {
  requireProject();
  const status = await call(api.getStatus);
  renderDashboard(status);
}

async function scanProject() {
  requireProject();
  log("Scanning project…");
  const { profile } = await call(api.scan);
  renderDashboard({ profile, manifest: null, vaultKeys: [], platform: "—" });
  log(`Scan complete — ${profile.framework}`, "success");
}

async function initVault() {
  requireProject();
  const pass = $("#vault-passphrase").value;
  if (!pass) throw new Error("Enter a passphrase");
  const { keys } = await call(api.initVault, pass);
  setVaultUi(true, keys);
  $("#vault-passphrase").value = "";
  log("Vault created successfully", "success");
}

async function unlockVault() {
  requireProject();
  const pass = $("#vault-passphrase").value;
  if (!pass) throw new Error("Enter a passphrase");
  const { keys } = await call(api.unlockVault, pass);
  setVaultUi(true, keys);
  $("#vault-passphrase").value = "";
  log("Vault unlocked", "success");
}

async function lockVault() {
  await call(api.lockVault);
  setVaultUi(false, []);
  log("Vault locked");
}

async function storeSecret() {
  requireVault();
  const key = $("#secret-key").value.trim();
  const value = $("#secret-value").value;
  if (!key || !value) throw new Error("Enter key and value");
  await call(api.vaultSet, key, value);
  $("#secret-key").value = "";
  $("#secret-value").value = "";
  await refreshVaultKeys();
  log(`Stored ${key}`, "success");
}

async function verifyKeys() {
  requireVault();
  log("Verifying Stripe keys…");
  const r = await call(api.verify);
  setOutput(els.stripeResult, [
    `Secret key      ${r.secretKey.valid ? "✓ PASS" : "✗ FAIL"}  ${r.secretKey.message}`,
    `Publishable key ${r.publishableKey.valid ? "✓ PASS" : "✗ FAIL"}  ${r.publishableKey.message}`,
    r.accountName ? `Account         ${r.accountName}` : "",
    r.country ? `Country         ${r.country}` : "",
    r.billingEnabled !== undefined ? `Billing         ${r.billingEnabled ? "enabled" : "check dashboard"}` : "",
  ].filter(Boolean).join("\n"));
  log("Verification complete", r.secretKey.valid ? "success" : "error");
}

async function runPipeline() {
  requireVault();
  log("Running Stripe pipeline…");
  const result = await call(api.runPipeline, {
    syncEnv: $("#opt-sync-env").checked,
    force: $("#opt-force").checked,
  });

  const lines = [];
  if (result.provision) {
    lines.push("── PROVISIONED ──");
    result.provision.prices.forEach((p) => {
      lines.push(`  ${p.tier.padEnd(14)} ${p.id}${p.reused ? "  (reused)" : "  (new)"}`);
    });
    result.provision.warnings.forEach((w) => lines.push(`  ⚠ ${w}`));
  }
  if (result.files?.length) {
    lines.push("\n── FILES ──");
    result.files.forEach((f) => lines.push(`  ${f.action.padEnd(8)} ${f.path}`));
  }
  setOutput(els.stripeResult, lines.join("\n") || "Pipeline completed successfully.");
  log("Pipeline complete", "success");
}

async function runDeploy() {
  requireVault();
  log("Running deploy pipeline…");
  const result = await call(api.deploy, {
    provisionPostgres: $("#opt-provision-db").checked,
    force: $("#opt-deploy-force").checked,
  });

  const lines = [
    `Readiness score   ${result.readinessScore}/100`,
    `Platform          ${result.platform}`,
    result.postgresProvisioned ? `PostgreSQL        ${result.postgresProvisioned.message}` : "",
    "",
    "── GENERATED ──",
    ...result.filesGenerated.map((f) => `  + ${f}`),
    "",
    "── NEXT STEPS ──",
    ...result.nextSteps.map((s) => `  → ${s}`),
  ].filter(Boolean);
  setOutput(els.deployResult, lines.join("\n"));
  log(`Deploy complete — ${result.readinessScore}/100 readiness`, "success");
}

async function runReadiness() {
  requireVault();
  log("Running readiness assessment…");
  const { checks, score } = await call(api.readiness);

  els.readinessScore.hidden = false;
  els.readinessScoreValue.textContent = String(score);
  updateScoreRing(score);

  const byCat = {};
  for (const c of checks) {
    (byCat[c.category] ??= []).push(c);
  }

  let html = "";
  for (const [cat, items] of Object.entries(byCat)) {
    html += `<div class="check-category">${escapeHtml(cat)}</div>`;
    for (const c of items) {
      const sym = c.status === "pass" ? "✓" : c.status === "warn" ? "!" : "✗";
      html += `
        <div class="check-card">
          <div class="check-card-header">
            <span class="check-status ${c.status}">${sym}</span>
            <span class="check-name">${escapeHtml(c.name)}</span>
          </div>
          <div class="check-message">${escapeHtml(c.message)}</div>
          ${c.fix && c.status !== "pass" ? `<div class="check-fix">Fix: ${escapeHtml(c.fix)}</div>` : ""}
        </div>`;
    }
  }
  els.readinessResult.innerHTML = html;
  log(`Readiness: ${score}/100`, score >= 80 ? "success" : "");
}

async function postgresProvision() {
  requireVault();
  const provider = $("#postgres-provider").value;
  log(`Provisioning ${provider}…`);
  const result = await call(api.postgresProvision, { provider });
  setOutput(els.deployResult, [
    result.message,
    `Provider       ${result.provider}`,
    `Reused         ${result.reused}`,
    `Schema applied ${result.schemaApplied}`,
  ].join("\n"));
  log(result.message, "success");
}

async function postgresStatus() {
  requireVault();
  const status = await call(api.postgresStatus);
  setOutput(els.deployResult, [
    `Connected  ${status.connected ? "yes" : "no"}`,
    status.message,
    status.manifest ? `Provider ${status.manifest.provider}\nSince     ${status.manifest.provisionedAt}` : "",
  ].filter(Boolean).join("\n"));
}

function renderDiagnoseReport(report) {
  els.diagnoseEmpty.hidden = true;
  els.diagnoseHero.hidden = false;
  els.healthScore.textContent = String(report.healthScore);

  els.healthBadge.classList.remove("good", "ok", "bad");
  if (report.healthScore >= 80) els.healthBadge.classList.add("good");
  else if (report.healthScore >= 50) els.healthBadge.classList.add("ok");
  else els.healthBadge.classList.add("bad");

  els.diagnoseSummary.textContent = report.summary;
  const errors = report.issues.filter((i) => i.severity === "error").length;
  const warnings = report.issues.filter((i) => i.severity === "warning").length;
  const fixable = report.issues.filter((i) => i.autoFixable).length;
  els.diagnoseStats.textContent = report.issues.length
    ? `${report.issues.length} issue(s) · ${errors} error(s) · ${warnings} warning(s) · ${fixable} auto-fixable`
    : "No issues found";

  if (report.issues.length === 0) {
    els.diagnoseIssues.innerHTML = `
      <div class="section-card" style="text-align:center;padding:32px">
        <div style="font-size:40px;margin-bottom:12px">✓</div>
        <strong>Stripe setup is healthy</strong>
        <p style="color:var(--text-muted);margin-top:8px;font-size:14px">No problems detected.</p>
      </div>`;
    return;
  }

  els.diagnoseIssues.innerHTML = report.issues.map((issue) => `
    <div class="issue-card ${issue.severity}" data-issue-id="${escapeHtml(issue.id)}">
      <div class="issue-category">${escapeHtml(issue.category)}</div>
      <div class="issue-header">
        <div class="issue-title">${escapeHtml(issue.title)}</div>
        ${issue.autoFixable ? '<span class="pill pill-success">Auto-fix</span>' : '<span class="pill pill-neutral">Manual</span>'}
      </div>
      <div class="issue-message">${escapeHtml(issue.message)}</div>
      <div class="issue-fix">→ ${escapeHtml(issue.fixHint)}</div>
      ${issue.autoFixable ? `<div class="issue-actions"><button class="btn-fix" data-fix-id="${escapeHtml(issue.id)}">Fix this</button></div>` : ""}
    </div>
  `).join("");

  els.diagnoseIssues.querySelectorAll("[data-fix-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.fixId;
      try {
        await fixIssues([id]);
      } catch (err) {
        log(err.message, "error");
      }
    });
  });
}

async function runDiagnose() {
  requireProject();
  log("Running Stripe diagnosis…");
  const report = await call(api.diagnose);
  renderDiagnoseReport(report);
  log(`Diagnosis complete — health ${report.healthScore}/100`, report.healthScore >= 80 ? "success" : "");
  return report;
}

async function fixIssues(issueIds) {
  if (issueIds?.length) requireVault();
  else requireVault();
  log(issueIds?.length ? `Fixing issue(s)…` : "Applying all auto-fixes…");
  const { repairs, report } = await call(api.fix, { issueIds: issueIds?.length ? issueIds : undefined });
  renderDiagnoseReport(report);
  for (const r of repairs) {
    log(`${r.success ? "Fixed" : "Failed"}: ${r.action} — ${r.message}`, r.success ? "success" : "error");
  }
  log(`Health now ${report.healthScore}/100`, report.healthScore >= 80 ? "success" : "");
}

function switchView(view) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  els.breadcrumb.textContent = VIEW_TITLES[view] ?? view;
}

function bindActions() {
  $$(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  $("#activity-toggle").addEventListener("click", () => {
    els.activityPanel.classList.toggle("collapsed");
  });

  els.stripeResult.dataset.placeholder = "Run verification or the full pipeline to see results here.";
  els.deployResult.dataset.placeholder = "Deploy results and next steps will appear here.";

  const actions = [
    ["#btn-select-project", selectProject],
    ["#btn-select-project-empty", selectProject],
    ["#btn-scan", scanProject],
    ["#btn-refresh-status", refreshStatus],
    ["#btn-init-vault", initVault],
    ["#btn-unlock-vault", unlockVault],
    ["#btn-lock", lockVault],
    ["#btn-store-secret", storeSecret],
    ["#btn-verify", verifyKeys],
    ["#btn-run-pipeline", runPipeline],
    ["#btn-deploy", runDeploy],
    ["#btn-readiness", runReadiness],
    ["#btn-postgres-provision", postgresProvision],
    ["#btn-postgres-status", postgresStatus],
    ["#btn-diagnose", runDiagnose],
    ["#btn-fix-all", () => fixIssues()],
  ];

  for (const [sel, fn] of actions) {
    const el = $(sel);
    if (!el) continue;
    el.addEventListener("click", async () => {
      try {
        await fn();
      } catch (err) {
        log(err.message, "error");
      }
    });
  }

  $("#vault-passphrase")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") unlockVault().catch((err) => log(err.message, "error"));
  });
}

bindActions();
setVaultUi(false);
setProjectUi(null);
log("Welcome — open a project to get started", "success");
