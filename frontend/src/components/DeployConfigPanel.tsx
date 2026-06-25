import { FormEvent, useEffect, useState } from "react";

import { deployApi, type DeployConfig } from "../api/client";

type Props = {
  projectSlug: string;
  hasLocalPath: boolean;
  onSaved: () => void;
  onError: (msg: string) => void;
};

export default function DeployConfigPanel({ projectSlug, hasLocalPath, onSaved, onError }: Props) {
  const [config, setConfig] = useState<DeployConfig | null>(null);
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!hasLocalPath) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await deployApi.getDeployConfig(projectSlug);
      setConfig(data.config);
      setExists(data.exists);
      onError("");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to load deploy config");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [projectSlug, hasLocalPath]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!config) return;
    setBusy(true);
    onError("");
    try {
      const data = await deployApi.saveDeployConfig(projectSlug, config);
      setConfig(data.config);
      setExists(true);
      onSaved();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (!hasLocalPath) {
    return (
      <section className="card">
        <h2>Deploy config</h2>
        <p className="muted">Set your real app local path to edit deploy.config.json.</p>
      </section>
    );
  }

  if (loading || !config) {
    return (
      <section className="card">
        <h2>Deploy config</h2>
        <p className="muted">{loading ? "Loading…" : "Could not load config."}</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>Deploy config</h2>
      <p className="muted">
        {exists ? "deploy.config.json in project root" : "No file yet — save to create deploy.config.json"}
      </p>
      <form className="settings-form compact" onSubmit={onSave}>
        <label>
          Production URL
          <input
            value={config.productionUrl}
            onChange={(e) => setConfig({ ...config, productionUrl: e.target.value })}
            placeholder="https://yourapp.com"
          />
        </label>
        <fieldset className="tier-fieldset">
          <legend>Environment URLs</legend>
          {(["test", "staging", "production"] as const).map((env) => (
            <label key={env} className="env-url-row">
              {env}
              <input
                value={config.environments?.[env]?.url || ""}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    environments: {
                      ...config.environments,
                      [env]: { url: e.target.value },
                    },
                  })
                }
                placeholder={env === "production" ? config.productionUrl : `https://${env}.yourapp.com`}
              />
            </label>
          ))}
        </fieldset>
        <label>
          Platform
          <select
            value={config.platform}
            onChange={(e) => setConfig({ ...config, platform: e.target.value as DeployConfig["platform"] })}
          >
            <option value="unknown">Auto-detect</option>
            <option value="vercel">Vercel</option>
            <option value="railway">Railway</option>
            <option value="fly">Fly.io</option>
            <option value="docker">Docker</option>
          </select>
        </label>
        <label>
          Postgres provider
          <select
            value={config.postgres.provider}
            onChange={(e) =>
              setConfig({
                ...config,
                postgres: {
                  ...config.postgres,
                  provider: e.target.value as DeployConfig["postgres"]["provider"],
                },
              })
            }
          >
            <option value="neon">Neon</option>
            <option value="supabase">Supabase</option>
            <option value="railway">Railway</option>
            <option value="self-hosted">Self-hosted</option>
          </select>
        </label>
        <label className="toggle-inline">
          <input
            type="checkbox"
            checked={config.postgres.autoProvision}
            onChange={(e) =>
              setConfig({
                ...config,
                postgres: { ...config.postgres, autoProvision: e.target.checked },
              })
            }
          />
          Auto-provision Postgres on deploy prep
        </label>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Saving…" : "Save deploy.config.json"}
        </button>
      </form>
    </section>
  );
}
