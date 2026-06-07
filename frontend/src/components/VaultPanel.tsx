import { useEffect, useState } from "react";

import { vaultApi, type VaultEntry } from "../api/client";

const STRIPE_KEYS = [
  { id: "STRIPE_SECRET_KEY", label: "Secret key", placeholder: "sk_live_…" },
  { id: "STRIPE_PUBLISHABLE_KEY", label: "Publishable key", placeholder: "pk_live_…" },
  { id: "STRIPE_WEBHOOK_SECRET", label: "Webhook secret", placeholder: "whsec_…" },
];

type VaultPanelProps = Readonly<{
  projectSlug: string;
  initialized: boolean;
  entries: VaultEntry[];
  onUpdate: (entries: VaultEntry[], initialized: boolean) => void;
  busy: string;
  setBusy: (v: string) => void;
  onError: (msg: string) => void;
}>;

export default function VaultPanel({
  projectSlug,
  initialized,
  entries,
  onUpdate,
  busy,
  setBusy,
  onError,
}: VaultPanelProps) {
  const [addingKey, setAddingKey] = useState<string | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<VaultEntry | null>(null);

  useEffect(() => {
    if (!deleteTarget) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setDeleteTarget(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [deleteTarget]);

  const entryMap = new Map(entries.map((e) => [e.key, e]));

  async function initVault() {
    setBusy("vault");
    onError("");
    try {
      const res = await vaultApi.init(projectSlug);
      onUpdate(res.entries, true);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Vault init failed");
    } finally {
      setBusy("");
    }
  }

  async function saveKey(keyName: string) {
    if (!draftValue.trim()) return;
    setBusy(`save-${keyName}`);
    onError("");
    try {
      const res = await vaultApi.set(projectSlug, keyName, draftValue.trim());
      onUpdate(res.entries, true);
      setDraftValue("");
      setAddingKey(null);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy("");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(`delete-${deleteTarget.key}`);
    onError("");
    try {
      const res = await vaultApi.remove(projectSlug, deleteTarget.key);
      onUpdate(res.entries, initialized);
      setDeleteTarget(null);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Delete failed");
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
          <p className="muted">Write-only secrets · AES-256-GCM · verified against Stripe</p>
        </div>
      </div>

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
                  {entry.verified ? (
                    <span className="vault-badge verified">Verified ✅</span>
                  ) : (
                    <span className="vault-badge unverified" title={entry.verificationMessage || undefined}>
                      Not verified
                    </span>
                  )}
                </div>
                <div className="vault-item-actions">
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
                <p className="vault-hint">Value is encrypted and never shown again after saving.</p>
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
