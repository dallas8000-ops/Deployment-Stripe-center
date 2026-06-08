import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { orgsApi } from "../api/client";

const PENDING_ORG_KEY = "github_install_org";

export default function GithubCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    async function complete() {
      const installationId = searchParams.get("installation_id");
      const state = searchParams.get("state") || "";
      const setupAction = searchParams.get("setup_action") || "";

      if (!installationId) {
        setError("Missing installation_id from GitHub redirect.");
        setBusy(false);
        return;
      }

      const orgSlug =
        (state.includes(":") ? state.split(":")[0] : state) ||
        localStorage.getItem(PENDING_ORG_KEY) ||
        "";

      if (!orgSlug) {
        setError("Could not determine organization — open Agency and install again.");
        setBusy(false);
        return;
      }

      try {
        await orgsApi.completeGithubInstall(orgSlug, {
          installation_id: Number(installationId),
          state,
          setup_action: setupAction,
        });
        localStorage.removeItem(PENDING_ORG_KEY);
        navigate("/agency", { replace: true });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to link GitHub App");
        setBusy(false);
      }
    }

    complete();
  }, [navigate, searchParams]);

  return (
    <div className="page page-center">
      <div className="card" style={{ maxWidth: 480 }}>
        <h1>GitHub App</h1>
        {busy && !error ? (
          <p className="muted">Linking installation to your organization…</p>
        ) : error ? (
          <>
            <div className="alert alert-error">{error}</div>
            <p>
              <Link to="/agency">Back to Agency</Link>
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
