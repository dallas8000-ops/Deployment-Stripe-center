import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function AccountSecurityPage() {
  const { user, refreshUser } = useAuth();
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [enrollSecret, setEnrollSecret] = useState("");
  const [enrollUri, setEnrollUri] = useState("");
  const [confirmCode, setConfirmCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");

  useEffect(() => {
    authApi
      .mfaStatus()
      .then((s) => setMfaEnabled(s.mfa_enabled))
      .catch(() => {});
  }, [user]);

  async function startEnroll() {
    setError("");
    setMessage("");
    setRecoveryCodes([]);
    setBusy(true);
    try {
      const data = await authApi.mfaEnrollStart();
      setEnrollSecret(data.secret);
      setEnrollUri(data.provisioning_uri);
      setMessage("Scan the URI in your authenticator app, then enter a code to confirm.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start MFA enrollment");
    } finally {
      setBusy(false);
    }
  }

  async function confirmEnroll(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await authApi.mfaEnrollConfirm(confirmCode.trim());
      setMfaEnabled(data.mfa_enabled);
      setRecoveryCodes(data.recovery_codes);
      setEnrollSecret("");
      setEnrollUri("");
      setConfirmCode("");
      setMessage("MFA enabled. Store recovery codes in a safe place — they are shown once.");
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setBusy(false);
    }
  }

  async function disableMfa(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await authApi.mfaDisable(disablePassword, disableCode.trim());
      setMfaEnabled(data.mfa_enabled);
      setDisablePassword("");
      setDisableCode("");
      setMessage("MFA disabled.");
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not disable MFA");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">
            <Link to="/">Projects</Link> / Account
          </p>
          <h1>Security</h1>
          <p className="muted">Two-factor authentication for {user?.email}</p>
        </div>
      </header>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <section className="panel">
        <h2>Authenticator app (TOTP)</h2>
        <p className="muted">
          Status: <strong>{mfaEnabled ? "Enabled" : "Not enabled"}</strong>
        </p>

        {!mfaEnabled && !enrollSecret && (
          <button type="button" className="btn btn-primary" disabled={busy} onClick={startEnroll}>
            Enable MFA
          </button>
        )}

        {enrollUri && (
          <form className="auth-form" onSubmit={confirmEnroll} style={{ marginTop: "1rem" }}>
            <p className="field-hint">
              Manual entry secret: <code>{enrollSecret}</code>
            </p>
            <p className="field-hint">
              URI: <code style={{ wordBreak: "break-all" }}>{enrollUri}</code>
            </p>
            <label className="field">
              <span>Verification code</span>
              <input
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value)}
                inputMode="numeric"
                placeholder="123456"
                required
              />
            </label>
            <button type="submit" className="btn btn-primary" disabled={busy}>
              Confirm MFA
            </button>
          </form>
        )}

        {recoveryCodes.length > 0 && (
          <div style={{ marginTop: "1rem" }}>
            <h3>Recovery codes</h3>
            <pre className="verify-pre">{recoveryCodes.join("\n")}</pre>
          </div>
        )}

        {mfaEnabled && (
          <form className="auth-form" onSubmit={disableMfa} style={{ marginTop: "1.5rem" }}>
            <h3>Disable MFA</h3>
            <label className="field">
              <span>Password</span>
              <input
                type="password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Authenticator code</span>
              <input
                value={disableCode}
                onChange={(e) => setDisableCode(e.target.value)}
                inputMode="numeric"
                required
              />
            </label>
            <button type="submit" className="btn btn-ghost" disabled={busy}>
              Disable MFA
            </button>
          </form>
        )}
      </section>
    </div>
  );
}
