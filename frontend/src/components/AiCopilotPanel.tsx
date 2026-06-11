import { useState } from "react";

import {
  aiApi,
  type FixCopilotItem,
  type HandoffPack,
  type ReadinessCoachItem,
} from "../api/client";
import type { DiagnosticReport } from "./DiagnosePanel";
import type { ReadinessCheck } from "./ReadinessPanel";
import EmptyState from "./EmptyState";

type Props = {
  projectSlug: string;
  diagnoseReport: DiagnosticReport | null;
  readinessChecks: ReadinessCheck[];
  onError: (msg: string) => void;
  onFixIssue: (issueId: string, action?: string | null) => void;
  onApplyNlConfig: () => void;
  onConfigApplied?: () => void;
  onCatalogApplied?: () => void;
  onOpenPrWithHandoff?: (handoff: HandoffPack) => void;
  fixing: string;
};

export default function AiCopilotPanel({
  projectSlug,
  diagnoseReport,
  readinessChecks,
  onError,
  onFixIssue,
  onApplyNlConfig,
  onConfigApplied,
  onCatalogApplied,
  onOpenPrWithHandoff,
  fixing,
}: Props) {
  const [busy, setBusy] = useState("");
  const [fixItems, setFixItems] = useState<FixCopilotItem[]>([]);
  const [coachItems, setCoachItems] = useState<ReadinessCoachItem[]>([]);
  const [nlInstruction, setNlInstruction] = useState("");
  const [businessDesc, setBusinessDesc] = useState("");
  const [webhookPayload, setWebhookPayload] = useState('{\n  "type": "checkout.session.completed"\n}');
  const [webhookEventId, setWebhookEventId] = useState("");
  const [handoff, setHandoff] = useState<HandoffPack | null>(null);
  const [output, setOutput] = useState("");
  const [provider, setProvider] = useState("");

  async function runFixCopilot() {
    setBusy("fix-copilot");
    onError("");
    try {
      const res = await aiApi.fixCopilot(projectSlug);
      setFixItems(res.items);
      setProvider(res.provider);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Fix copilot failed");
    } finally {
      setBusy("");
    }
  }

  async function runReadinessCoach() {
    setBusy("coach");
    onError("");
    try {
      const res = await aiApi.readinessCoach(projectSlug);
      setCoachItems(res.items);
      setProvider(res.provider);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Readiness coach failed");
    } finally {
      setBusy("");
    }
  }

  async function runNlConfig(apply: boolean) {
    setBusy(apply ? "nl-apply" : "nl-preview");
    onError("");
    try {
      const res = await aiApi.nlConfig(projectSlug, nlInstruction, apply);
      setOutput(JSON.stringify({ stripe: res.stripeConfig, deploy: res.deployConfig, written: res.written }, null, 2));
      setProvider(res.provider);
      if (apply) {
        onApplyNlConfig();
        onConfigApplied?.();
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "NL config failed");
    } finally {
      setBusy("");
    }
  }

  async function runCatalog(apply: boolean) {
    setBusy(apply ? "catalog-apply" : "catalog");
    onError("");
    try {
      const res = await aiApi.catalogStrategist(projectSlug, businessDesc, apply);
      setOutput(JSON.stringify(res.stripeConfig, null, 2));
      setProvider(res.provider);
      if (apply) {
        onApplyNlConfig();
        onCatalogApplied?.();
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Catalog strategist failed");
    } finally {
      setBusy("");
    }
  }

  async function runHandoff() {
    setBusy("handoff");
    onError("");
    try {
      const res = await aiApi.handoffPack(projectSlug);
      setHandoff(res);
      setProvider(res.provider);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Handoff pack failed");
    } finally {
      setBusy("");
    }
  }

  async function runWebhookAssistant() {
    setBusy("webhook");
    onError("");
    try {
      const res = await aiApi.webhookIncident(projectSlug, {
        eventId: webhookEventId.trim() || undefined,
        payload: webhookEventId.trim() ? undefined : webhookPayload,
      });
      const prefix = res.fetchedFromStripe ? `[fetched ${res.eventId}]\n\n` : "";
      setOutput(prefix + res.analysis);
      setProvider(res.provider);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Webhook analysis failed");
    } finally {
      setBusy("");
    }
  }

  const fixMap = new Map(fixItems.map((i) => [i.issueId, i]));

  return (
    <section className="card ai-copilot-card">
      <h2>AI copilot</h2>
      <p className="muted">
        Sanitized context only — vault secrets never sent to AI. Store OPENAI_API_KEY or ANTHROPIC_API_KEY in vault.
        {provider && ` · last: ${provider}`}
      </p>

      <div className="copilot-section">
        <h3>1. Fix copilot</h3>
        <p className="muted">Explain diagnose issues and one-click repair.</p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={runFixCopilot} disabled={busy === "fix-copilot" || !diagnoseReport}>
          {busy === "fix-copilot" ? "Explaining…" : "Explain issues"}
        </button>
        {!diagnoseReport ? (
          <div style={{ marginTop: "16px" }}>
            <EmptyState
              icon="🔍"
              title="Run diagnostics first"
              description="Get copilot suggestions after running a diagnostics scan"
            />
          </div>
        ) : diagnoseReport.issues.length === 0 ? (
          <div style={{ marginTop: "16px" }}>
            <EmptyState
              icon="✅"
              title="No issues found"
              description="Your Stripe setup looks good — diagnostics found no problems"
            />
          </div>
        ) : fixItems.length > 0 ? (
          <ul className="copilot-fix-list">
            {diagnoseReport.issues.map((issue) => {
              const copilot = fixMap.get(issue.id);
              return (
                <li key={issue.id} className="copilot-fix-item">
                  <strong>{issue.title}</strong>
                  <p>{copilot?.explanation || issue.message}</p>
                  {copilot?.autoFixable && copilot.fixAction && (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={!!fixing}
                      onClick={() => onFixIssue(issue.id, copilot.fixAction)}
                    >
                      Apply fix ({copilot.fixAction})
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      <div className="copilot-section">
        <h3>2. Natural language → config</h3>
        <textarea
          className="copilot-textarea"
          rows={2}
          placeholder='e.g. "Three tiers $9/$29/$99 yearly, Vercel, Neon us-east"'
          value={nlInstruction}
          onChange={(e) => setNlInstruction(e.target.value)}
        />
        <div className="option-row compact">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => runNlConfig(false)} disabled={!nlInstruction || busy === "nl-preview"}>
            Preview
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => runNlConfig(true)} disabled={!nlInstruction || busy === "nl-apply"}>
            Apply & write configs
          </button>
        </div>
      </div>

      <div className="copilot-section">
        <h3>3. Readiness coach</h3>
        <button type="button" className="btn btn-secondary btn-sm" onClick={runReadinessCoach} disabled={busy === "coach" || readinessChecks.length === 0}>
          {busy === "coach" ? "Coaching…" : "Coach failing checks"}
        </button>
        {coachItems.length > 0 && (
          <ul className="copilot-coach-list">
            {coachItems.map((item) => (
              <li key={item.checkId}>
                <strong>{item.checkId}</strong>
                <p>{item.coachSteps}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="copilot-section">
        <h3>4. Handoff pack</h3>
        <div className="option-row compact">
          <button type="button" className="btn btn-secondary btn-sm" onClick={runHandoff} disabled={busy === "handoff"}>
            {busy === "handoff" ? "Generating…" : "Generate PR + runbook"}
          </button>
          {handoff && onOpenPrWithHandoff && (
            <button type="button" className="btn btn-primary btn-sm" onClick={() => onOpenPrWithHandoff(handoff)}>
              Open PR with this pack
            </button>
          )}
        </div>
        {handoff && (
          <div className="handoff-tabs">
            <details open>
              <summary>PR description</summary>
              <pre className="verify-pre">{handoff.prDescription}</pre>
            </details>
            <details>
              <summary>Ops runbook</summary>
              <pre className="verify-pre">{handoff.opsRunbook}</pre>
            </details>
            <details>
              <summary>Test checklist</summary>
              <pre className="verify-pre">{handoff.testChecklist}</pre>
            </details>
          </div>
        )}
      </div>

      <div className="copilot-section">
        <h3>5. Catalog strategist</h3>
        <input
          placeholder="Business description (optional)"
          value={businessDesc}
          onChange={(e) => setBusinessDesc(e.target.value)}
        />
        <div className="option-row compact">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => runCatalog(false)} disabled={busy === "catalog"}>
            Propose tiers
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => runCatalog(true)} disabled={busy === "catalog-apply"}>
            Write stripe.config.json
          </button>
        </div>
      </div>

      <div className="copilot-section">
        <h3>6. Webhook incident assistant</h3>
        <label>
          Stripe event ID
          <input
            placeholder="evt_… (fetches from Stripe, sanitized)"
            value={webhookEventId}
            onChange={(e) => setWebhookEventId(e.target.value)}
          />
        </label>
        <p className="muted vault-hint">Or paste redacted webhook JSON — remove secrets before sending.</p>
        <textarea
          className="copilot-textarea"
          rows={4}
          value={webhookPayload}
          onChange={(e) => setWebhookPayload(e.target.value)}
          disabled={!!webhookEventId.trim()}
        />
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={runWebhookAssistant}
          disabled={busy === "webhook" || (!webhookEventId.trim() && !webhookPayload.trim())}
        >
          {busy === "webhook" ? "Analyzing…" : webhookEventId.trim() ? "Fetch & analyze" : "Analyze event"}
        </button>
      </div>

      {output && (
        <div className="copilot-section">
          <h3>Output</h3>
          <pre className="verify-pre ai-pre">{output}</pre>
        </div>
      )}
    </section>
  );
}
