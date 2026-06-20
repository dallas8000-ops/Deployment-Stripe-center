import { FormEvent, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { APP_LOGIN_SUBTITLE } from "../config/branding";
import AuthLayout from "../components/AuthLayout";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const passwordRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState(
    () => localStorage.getItem("last_login_email") || ""
  );
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
      await login(email.trim(), password);
      localStorage.setItem("last_login_email", email.trim());
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  function clearPassword() {
    if (passwordRef.current) {
      passwordRef.current.value = "";
    }
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
