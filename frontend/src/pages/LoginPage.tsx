import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { APP_LOGIN_SUBTITLE } from "../config/branding";
import AuthLayout from "../components/AuthLayout";

export default function LoginPage() {
  const { login, refreshUser } = useAuth();
  const navigate = useNavigate();
  const passwordRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState(
    () => localStorage.getItem("last_login_email") || ""
  );
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [ssoLoginUrl, setSsoLoginUrl] = useState<string | null>(null);

  useEffect(() => {
    authApi
      .ssoConfig()
      .then((cfg) => {
        if (cfg.enabled && cfg.login_url) {
          setSsoLoginUrl(cfg.login_url);
        }
      })
      .catch(() => {});
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const password = passwordRef.current?.value ?? "";
    if (!password.trim()) {
      setError("Enter your password (click Clear if the browser filled the wrong one).");
      return;
    }
    setBusy(true);
    try {
      const result = await login(email.trim(), password);
      if (result.mfa_required && result.mfa_token) {
        setMfaToken(result.mfa_token);
        return;
      }
      localStorage.setItem("last_login_email", email.trim());
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  async function onMfaSubmit(e: FormEvent) {
    e.preventDefault();
    if (!mfaToken) return;
    setError("");
    setBusy(true);
    try {
      await authApi.verifyMfa(mfaToken, mfaCode.trim());
      await refreshUser();
      localStorage.setItem("last_login_email", email.trim());
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setBusy(false);
    }
  }

  function clearPassword() {
    if (passwordRef.current) {
      passwordRef.current.value = "";
    }
  }

  if (mfaToken) {
    return (
      <AuthLayout
        title="Two-factor authentication"
        subtitle="Enter the 6-digit code from your authenticator app."
        footer={
          <button type="button" className="btn btn-ghost" onClick={() => setMfaToken(null)}>
            Back to password
          </button>
        }
      >
        <form className="auth-form" onSubmit={onMfaSubmit}>
          {error && <div className="alert alert-error">{error}</div>}
          <label className="field">
            <span>Authenticator code</span>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              placeholder="123456"
              maxLength={8}
              required
              autoFocus
            />
          </label>
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "Verifying…" : "Verify"}
          </button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle={APP_LOGIN_SUBTITLE}
      footer={
        <>
          No account? <Link to="/register">Create one</Link>
        </>
      }
    >
      {ssoLoginUrl && (
        <p className="page-actions" style={{ marginBottom: "1rem" }}>
          <a className="btn btn-secondary btn-block" href={ssoLoginUrl}>
            Sign in with SSO
          </a>
        </p>
      )}
      <form className="auth-form" onSubmit={onSubmit} autoComplete="off">
        {error && <div className="alert alert-error">{error}</div>}
        <label className="field">
          <span>Email</span>
          <input
            type="email"
            name="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="email"
            required
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            ref={passwordRef}
            key={showPassword ? "text" : "password"}
            type={showPassword ? "text" : "password"}
            name="password"
            defaultValue=""
            placeholder="Type your password"
            autoComplete="new-password"
            data-1p-ignore="true"
            data-lpignore="true"
            required
          />
          <span className="field-hint">
            If dots appear before you type, click <strong>Clear</strong> — browser autofill often uses the wrong password.
          </span>
          <div className="page-actions compact-actions" style={{ marginTop: "0.35rem" }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={clearPassword}>
              Clear
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowPassword((v) => !v)}
            >
              {showPassword ? "Hide" : "Show"} password
            </button>
          </div>
        </label>
        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthLayout>
  );
}
