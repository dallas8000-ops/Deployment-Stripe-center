import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { setTokens } from "../api/client";
import AuthLayout from "../components/AuthLayout";

export default function SsoCallbackPage() {
  const navigate = useNavigate();

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "");
    const params = new URLSearchParams(hash);
    const access = params.get("access");
    const refresh = params.get("refresh");
    if (access && refresh) {
      setTokens(access, refresh);
      navigate("/", { replace: true });
      return;
    }
    navigate("/login", { replace: true });
  }, [navigate]);

  return (
    <AuthLayout title="Signing in" subtitle="Completing SSO…">
      <p className="muted">Redirecting…</p>
    </AuthLayout>
  );
}
