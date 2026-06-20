import { useEffect, useState } from "react";

import { vaultApi, type SecretSourceInfo, type VaultEntry } from "../api/client";

const HUB_SLUG = "stripe-installer";

const STRIPE_KEYS = [
  { id: "STRIPE_SECRET_KEY", label: "Secret key", placeholder: "sk_live_…", copyable: false },
  { id: "STRIPE_PUBLISHABLE_KEY", label: "Publishable key", placeholder: "pk_live_…", copyable: true },
  { id: "STRIPE_WEBHOOK_SECRET", label: "Webhook secret", placeholder: "whsec_…", copyable: true },
];

type VaultPanelProps = Readonly<{
  projectSlug: string;
  initialized: boolean;
  entries: VaultEntry[];
  onUpdate: (entries: VaultEntry[], initialized: boolean) => void;
  busy: string;
  setBusy: (v: string) => void;
}>;

export default function VaultPanel({
  projectSlug,
  initialized,
  entries,
  onUpdate,
  busy,
  setBusy,
}: VaultPanelProps) {
  const [addingKey, setAddingKey] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<VaultEntry | null>(null);
  const [sources, setSources] = useState<SecretSourceInfo[]>([]);
  const [legacyPassphrase, setLegacyPassphrase] = useState("");
  const [showLegacyPass, setShowLegacyPass] = useState(false);
  const [vaultError, setVaultError] = useState("");
  const [vaultNotice, setVaultNotice] = useState("");

  const isHub = projectSlug === HUB_SLUG;
  const hasStripeSecret = entries.some((e) => e.key === "STRIPE_SECRET_KEY" && e.readable !== false);

  useEffect(() => {
    if (!initialized || isHub || hasStripeSecret) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await vaultApi.pullFromHub(projectSlug);
        if (!cancelled && res.copied.length > 0) {
          onUpdate(res.entries, true);
          setVaultNotice(res.message);
        }
      } catch {
        /* hub empty or not configured — user adds keys on hub */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialized, isHub, hasStripeSecret, projectSlug, onUpdate]);

  useEffect(() => {
    if (!initialized) return;
    let cancelled = false;
    vaultApi
      .sources(projectSlug)
      .then((res) => {
        if (!cancelled) setSources(res.sources);
      })
      .catch(() => {
        if (!cancelled) setSources([]);
      });
    return () => {
      cancelled = true;
    };
  }, [initialized, projectSlug]);

  useEffect(() => {
    if (!deleteTarget) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setDeleteTarget(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [deleteTarget]);

  const entryMap = new Map(entries.map((e) => [e.key, e]));
  const unreadableCount = entries.filter((e) => e.readable === false).length;

  async function initVault() {
    setBusy("vault");
    setVaultError("");
    try {
      const res = await vaultApi.init(projectSlug);
      onUpdate(res.entries, true);
    } catch (err) {
      setVaultError(err instanceof Error ? err.message : "Vault init failed");
    } finally {
      setBusy("");
    }
  }

  async function copyKey(keyName: string) {
    setBusy(`copy-${keyName}`);
    setVaultError("");
    try {
      const res = await vaultApi.copy(projectSlug, keyName);
      await navigator.clipboard.writeText(res.value);
      setVaultError("");
    } catch (err) {
      setVaultError(err instanceof Error ? err.message : "Copy failed");
    } finally {
      setBusy("");
    }
  }

  async function saveKey(keyName: string) {
    if (!draftValue.trim()) return;
    setBusy(`save-${keyName}`);
    setVaultError("");
    try {
      const res = await vaultApi.set(projectSlug, keyName, draftValue.trim());
      onUpdate(res.entries, true);
      setDraftValue("");
      setAddingKey(null);
    } catch (err) {
      setVaultError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy("");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(`delete-${deleteTarget.key}`);
    setVaultError("");
    try {
      const res = await vaultApi.remove(projectSlug, deleteTarget.key);
      onUpdate(res.entries, initialized);
      setDeleteTarget(null);
    } catch (err) {
      setVaultError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy("");
    }
  }

  function startAdd(keyId: string) {
    setAddingKey(keyId);
    setDraftValue("");
  }

  function cancelAdd() {
    setAddingKey(null);
    setDraftValue("");
  }

  async function pullFromHub() {
    setBusy("pull-hub");
    setVaultError("");
    setVaultNotice("");
    try {
      const res = await vaultApi.pullFromHub(projectSlug);
      onUpdate(res.entries, true);
      setVaultNotice(res.message);
    } catch (err) {
      setVaultError(err instanceof Error ? err.message : "Could not pull keys from Automation Center");
    } finally {
      setBusy("");
    }
  }

  async function importFromEnv() {
    setBusy("vault-import");
    setVaultError("");
    try {
      const res = await vaultApi.importFromEnv(projectSlug);
      onUpdate(res.entries, true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Import failed";
      setVaultError(
        msg.includes("No env file")
          ? "No .env in this repo — use Pull from Automation Center (keys live on the hub project)."
          : msg
      );
    } finally {
      setBusy("");
    }
  }

  async function importAll() {
    setBusy("vault-import-all");
    setVaultError("");
    try {
      const res = await vaultApi.importAll(projectSlug, {
        legacyPassphrase: legacyPassphrase || undefined,
      });
      onUpdate(res.entries, true);
      if (res.errors.length) {
        setVaultError(res.errors.join(" "));
      } else {
        setVaultError("");
      }
      const src = await vaultApi.sources(projectSlug);
      setSources(src.sources);
    } catch (err) {
      setVaultError(err instanceof Error ? err.message : "Import all failed");
    } finally {
      setBusy("");
    }
  }

  const legacySource = sources.find((s) => s.kind === "legacy_vault" && s.status === "needs_passphrase");

  if (!initialized) {
    return (
      <section className="card vault-card">
        <div className="vault-header">
          <div className="vault-lock-icon" aria-hidden>
            🔐
          </div>
          <div>
            <h2>Secure vault</h2>
            <p className="muted">Encrypted storage for Stripe keys. Write-only — values are never shown again.</p>
          </div>
        </div>
        <button type="button" className="btn btn-primary" onClick={initVault} disabled={busy === "vault"}>
          {busy === "vault" ? "Unlocking…" : "Unlock vault"}
        </button>
      </section>
    );
  }

  return (
    <section className="card vault-card">
      <div className="vault-header">
        <div className="vault-lock-icon unlocked" aria-hidden>
          🔐
        </div>
        <div>
          <h2>Secure vault</h2>
          <p className="muted">
            Secrets live in <code>~/.stripe-installer/</code> on this machine only — never pushed to git.
            After saving, only masked values are shown. Use <strong>Copy</strong> for publishable/webhook keys, or{" "}
            <strong>Sync keys to billing projects</strong> in Setup Hub for secret keys.
          </p>
        </div>
        <div className="vault-item-actions">
          {!isHub && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => void pullFromHub()}
              disabled={busy === "pull-hub" || !!busy}
            >
              {busy === "pull-hub" ? "Pulling…" : "Pull from Automation Center"}
            </button>
          )}
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={importAll}
            disabled={busy === "vault-import-all" || !!busy}
            title="Scan legacy CLI vault, .env files, and copy into ~/.stripe-installer/projects/"
          >
            {busy === "vault-import-all" ? "Importing…" : "Import all sources"}
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={importFromEnv}
            disabled={busy === "vault-import" || !!busy}
            title="Import from .env.local or .env only"
          >
            {busy === "vault-import" ? "Importing…" : "Import .env"}
          </button>
        </div>
      </div>

      {vaultNotice ? <div className="alert">{vaultNotice}</div> : null}

      {vaultError ? (
        <div className="alert alert-error" role="alert">
          {vaultError}
        </div>
      ) : null}

      {sources.length > 0 ? (
        <details className="vault-sources-panel">
          <summary>Where secrets are stored ({sources.filter((s) => s.keyCount > 0).length} with keys)</summary>
          <ul className="vault-sources-list">
            {sources.map((src) => (
              <li key={`${src.kind}-${src.path}`}>
                <strong>{src.label}</strong>
                <span className={`vault-badge ${src.status === "ready" ? "verified" : "unverified"}`}>
                  {src.status.replace("_", " ")}
                </span>
                {src.keyCount > 0 ? (
                  <span className="muted"> — {src.keyCount} key(s): {src.keys.join(", ")}</span>
                ) : null}
                <div className="muted vault-source-path">{src.path}</div>
                {src.note ? <div className="muted">{src.note}</div> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {legacySource ? (
        <div className="vault-legacy-pass">
          <label>
            Legacy CLI vault passphrase
            <input
              type={showLegacyPass ? "text" : "password"}
              value={legacyPassphrase}
              onChange={(e) => setLegacyPassphrase(e.target.value)}
              placeholder="Passphrase from old stripe-installer vault unlock"
              autoComplete="off"
            />
          </label>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowLegacyPass((v) => !v)}>
            {showLegacyPass ? "Hide" : "Show"}
          </button>
          <p className="vault-hint">
            Found <code>.stripe-installer/vault.enc.json</code> in the project folder — enter the passphrase, then
            click Import all sources.
          </p>
        </div>
      ) : null}

      {unreadableCount > 0 ? (
        <div className="alert alert-warn" role="alert">
          <strong>{unreadableCount} stored key(s) cannot be decrypted.</strong> Secrets are backed up under{" "}
          <code>~/.stripe-installer/projects/</code> on this machine. Re-save keys once (or Import from .env) and they
          will persist across setup runs. The master key is in <code>~/.stripe-installer/vault-master-key</code> — back
          that file up; do not put it in git.
        </div>
      ) : null}

      <ul className="vault-items">
        {STRIPE_KEYS.map((def) => {
          const entry = entryMap.get(def.id);
          const isAdding = addingKey === def.id;
          const isSaving = busy === `save-${def.id}`;

          if (entry && !isAdding) {
            return (
              <li key={def.id} className="vault-item stored">
                <div className="vault-item-main">
                  <span className="vault-item-label">{def.label}</span>
                  <code className="vault-item-mask">{entry.display}</code>
                  {entry.readable === false ? (
                    <span className="vault-badge unverified" title="Cannot decrypt — check ~/.stripe-installer vault backup">
                      Unreadable
                    </span>
                  ) : entry.verified ? (
                    <span className="vault-badge verified">Verified ✅</span>
                  ) : (
                    <span className="vault-badge unverified" title={entry.verificationMessage || undefined}>
                      Not verified
                    </span>
                  )}
                </div>
                <div className="vault-item-actions">
                  {def.copyable && entry.readable !== false ? (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => void copyKey(def.id)}
                      disabled={!!busy}
                    >
                      {busy === `copy-${def.id}` ? "Copied…" : "Copy"}
                    </button>
                  ) : null}
                  {!def.copyable && entry.readable !== false ? (
                    <a
                      href="https://dashboard.stripe.com/apikeys"
                      target="_blank"
                      rel="noreferrer"
                      className="btn btn-ghost btn-sm"
                    >
                      Stripe Dashboard
                    </a>
                  ) : null}
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => startAdd(def.id)}
                    disabled={!!busy}
                  >
                    Replace
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm vault-delete-btn"
                    onClick={() => setDeleteTarget(entry)}
                    disabled={!!busy}
                  >
                    Delete
                  </button>
                </div>
              </li>
            );
          }

          if (isAdding || !entry) {
            return (
              <li key={def.id} className="vault-item editing">
                <label className="vault-item-label">{def.label}</label>
                <input
                  type="password"
                  className="vault-secret-input"
                  placeholder={def.placeholder}
                  value={draftValue}
                  onChange={(e) => setDraftValue(e.target.value)}
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  aria-label={`${def.label} (write-only)`}
                />
                <p className="vault-hint">
                  {def.id === "STRIPE_SECRET_KEY"
                    ? "Secret keys are never shown after save — copy sk_live_ from Stripe Dashboard only."
                    : "Value is encrypted and never shown again after saving."}
                </p>
                <div className="vault-item-actions">
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={!draftValue.trim() || isSaving}
                    onClick={() => saveKey(def.id)}
                  >
                    {isSaving ? "Saving…" : "Save to vault"}
                  </button>
                  {(entry || addingKey) && (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={cancelAdd} disabled={isSaving}>
                      Cancel
                    </button>
                  )}
                </div>
              </li>
            );
          }

          return null;
        })}

        {entries
          .filter((e) => !STRIPE_KEYS.some((d) => d.id === e.key))
          .map((entry) => (
            <li key={entry.key} className="vault-item stored">
              <div className="vault-item-main">
                <span className="vault-item-label">{entry.key}</span>
                <code className="vault-item-mask">{entry.display}</code>
                {entry.verified && <span className="vault-badge verified">Stored ✅</span>}
              </div>
              <div className="vault-item-actions">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm vault-delete-btn"
                  onClick={() => setDeleteTarget(entry)}
                  disabled={!!busy}
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
      </ul>

      {deleteTarget && (
        <div className="vault-modal-backdrop">
          <button
            type="button"
            className="vault-modal-scrim"
            aria-label="Close delete confirmation"
            onClick={() => setDeleteTarget(null)}
          />
          <div
            className="vault-modal"
            role="alertdialog"
            aria-labelledby="vault-delete-title"
            aria-describedby="vault-delete-desc"
          >
            <h3 id="vault-delete-title">Delete secret?</h3>
            <p id="vault-delete-desc">
              Remove <strong>{deleteTarget.key}</strong> ({deleteTarget.display}) from the vault. This cannot be
              undone.
            </p>
            <div className="vault-modal-actions">
              <button type="button" className="btn btn-ghost" onClick={() => setDeleteTarget(null)} disabled={!!busy}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={confirmDelete}
                disabled={busy === `delete-${deleteTarget.key}`}
              >
                {busy === `delete-${deleteTarget.key}` ? "Deleting…" : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
