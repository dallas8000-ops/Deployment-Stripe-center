import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { authApi } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import AuthLayout from "../components/AuthLayout";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inviteToken = searchParams.get("invite") || "";

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [inviteOrg, setInviteOrg] = useState<string | null>(null);

  useEffect(() => {
    if (!inviteToken) return;
    authApi
      .invitePreview(inviteToken)
      .then((preview) => {
        if (preview.valid && preview.email) {
          setEmail(preview.email);
          setInviteOrg(preview.organization || null);
        } else {
          setError("Invite link is invalid or expired.");
        }
      })
      .catch(() => setError("Could not load invite."));
  }, [inviteToken]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await register(email, password, displayName || undefined, inviteToken || undefined);
      navigate(inviteOrg ? "/agency" : "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title={inviteOrg ? `Join ${inviteOrg}` : "Create account"}
      subtitle={
        inviteOrg
          ? "Create your account to join the organization"
          : "Start securing Stripe keys for your projects"
      }
      footer={
        <>
          Already have an account? <Link to="/login">Sign in</Link>
        </>
      }
    >
      <form className="auth-form" onSubmit={onSubmit}>
        {error && <div className="alert alert-error">{error}</div>}
        {inviteOrg && !error && (
          <div className="alert">
            You were invited to <strong>{inviteOrg}</strong>. Use the email address from your invite.
          </div>
        )}
        <label className="field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="email"
            readOnly={!!inviteToken && !!inviteOrg}
            required
          />
        </label>
        <label className="field">
          <span>Display name</span>
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Your name"
            autoComplete="name"
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            name="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Choose a password (8+ characters)"
            minLength={8}
            autoComplete="off"
            data-1p-ignore="true"
            data-lpignore="true"
            required
          />
          <span className="field-hint">Use your own password — ignore browser “suggest strong password” if you prefer.</span>
        </label>
        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? "Creating account…" : inviteOrg ? "Join organization" : "Create account"}
        </button>
      </form>
    </AuthLayout>
  );
}
