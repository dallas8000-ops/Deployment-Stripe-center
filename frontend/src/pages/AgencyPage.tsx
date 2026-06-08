import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  agencyApi,
  orgsApi,
  type AgencyBillingInfo,
  type OrgMember,
  type Organization,
  type PendingInvite,
} from "../api/client";

const ROLES = ["viewer", "member", "admin", "owner"] as const;
const PENDING_ORG_KEY = "github_install_org";

export default function AgencyPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([]);
  const [inviteNotice, setInviteNotice] = useState("");
  const [dashboard, setDashboard] = useState<Awaited<ReturnType<typeof agencyApi.dashboard>> | null>(null);
  const [billing, setBilling] = useState<AgencyBillingInfo | null>(null);
  const [orgName, setOrgName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<string>("member");
  const [selectedOrg, setSelectedOrg] = useState<string>("");
  const [githubInstallId, setGithubInstallId] = useState("");
  const [githubAccount, setGithubAccount] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const selected = orgs.find((o) => o.slug === selectedOrg);
  const canAdmin = selected?.my_role === "owner" || selected?.my_role === "admin";

  async function loadMembers(orgSlug: string) {
    try {
      const res = await orgsApi.members(orgSlug);
      setMembers(res.members);
    } catch {
      setMembers([]);
    }
    try {
      const pending = await orgsApi.pendingInvites(orgSlug);
      setPendingInvites(pending.invites);
    } catch {
      setPendingInvites([]);
    }
  }

  async function load() {
    setLoading(true);
    try {
      const [dash, list] = await Promise.all([agencyApi.dashboard(), orgsApi.list()]);
      setDashboard(dash);
      setBilling(dash.billing ?? null);
      setOrgs(list);
      const slug = selectedOrg || list[0]?.slug || "";
      if (slug && slug !== selectedOrg) setSelectedOrg(slug);
      if (slug) {
        await loadMembers(slug);
        const org = list.find((o) => o.slug === slug);
        setGithubInstallId(org?.github_installation_id ? String(org.github_installation_id) : "");
        setGithubAccount(org?.github_account || "");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selectedOrg) return;
    loadMembers(selectedOrg);
    const org = orgs.find((o) => o.slug === selectedOrg);
    setGithubInstallId(org?.github_installation_id ? String(org.github_installation_id) : "");
    setGithubAccount(org?.github_account || "");
  }, [selectedOrg, orgs]);

  async function createOrg(e: FormEvent) {
    e.preventDefault();
    setBusy("create");
    setError("");
    try {
      await orgsApi.create(orgName);
      setOrgName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy("");
    }
  }

  async function inviteMember(e: FormEvent) {
    e.preventDefault();
    if (!selectedOrg) return;
    setBusy("invite");
    setError("");
    setInviteNotice("");
    try {
      const res = await orgsApi.invite(selectedOrg, inviteEmail, inviteRole);
      setInviteEmail("");
      if (res && typeof res === "object" && "pending" in res && res.pending) {
        const msg = res.emailSent
          ? `Invite email sent to ${res.email}.`
          : `Share this link with ${res.email}:`;
        setInviteNotice(`${msg} ${res.inviteUrl}`);
      }
      await loadMembers(selectedOrg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invite failed");
    } finally {
      setBusy("");
    }
  }

  async function revokeInvite(inviteId: string) {
    if (!selectedOrg) return;
    setBusy(`revoke-${inviteId}`);
    try {
      await orgsApi.revokeInvite(selectedOrg, inviteId);
      await loadMembers(selectedOrg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revoke failed");
    } finally {
      setBusy("");
    }
  }

  function copyInviteLink(url: string) {
    navigator.clipboard.writeText(url).catch(() => {});
    setInviteNotice("Invite link copied to clipboard.");
  }

  async function changeRole(memberId: string, role: string) {
    if (!selectedOrg) return;
    setBusy(`role-${memberId}`);
    setError("");
    try {
      await orgsApi.updateMember(selectedOrg, memberId, role);
      await loadMembers(selectedOrg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update role failed");
    } finally {
      setBusy("");
    }
  }

  async function removeMember(memberId: string) {
    if (!selectedOrg || !window.confirm("Remove this member?")) return;
    setBusy(`rm-${memberId}`);
    setError("");
    try {
      await orgsApi.removeMember(selectedOrg, memberId);
      await loadMembers(selectedOrg);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remove failed");
    } finally {
      setBusy("");
    }
  }

  async function installGithubApp() {
    if (!selectedOrg) return;
    setBusy("github-install");
    setError("");
    try {
      const res = await orgsApi.githubInstallUrl(selectedOrg);
      if (!res.configured || !res.url) {
        setError(res.message || "GitHub App install URL not configured on server.");
        return;
      }
      localStorage.setItem(PENDING_ORG_KEY, selectedOrg);
      window.location.href = res.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Install URL failed");
    } finally {
      setBusy("");
    }
  }

  async function linkGithub(e: FormEvent) {
    e.preventDefault();
    if (!selectedOrg || !githubInstallId) return;
    setBusy("github");
    setError("");
    try {
      await orgsApi.linkGithub(selectedOrg, Number(githubInstallId), githubAccount);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Link GitHub failed");
    } finally {
      setBusy("");
    }
  }

  const orgProjects = dashboard?.projects.filter((p) => p.organization_slug === selectedOrg) || [];
  const orgBilling = billing?.organizations.find((o) => o.slug === selectedOrg);
  const showUpgradeBanner =
    billing?.saasConfigured &&
    orgBilling &&
    !orgBilling.subscriptionActive &&
    (orgBilling.memberCount >= (billing?.freeMemberLimit ?? 3) ||
      orgBilling.projectCount >= (billing?.freeProjectLimit ?? 5));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Agency dashboard</h1>
          <p className="muted">Organizations, team roles, GitHub App, and shared projects.</p>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showUpgradeBanner && (
        <div className="alert">
          Free tier: up to {billing?.freeMemberLimit} members and {billing?.freeProjectLimit} org projects.{" "}
          <Link to="/billing">Upgrade organization billing</Link> to add more.
        </div>
      )}

      <>
          <section className="stats-row">
            <div className="stat-card">
              <span className="muted">Organizations</span>
              <strong>{dashboard?.stats.organizationCount ?? 0}</strong>
            </div>
            <div className="stat-card">
              <span className="muted">Accessible projects</span>
              <strong>{dashboard?.stats.projectCount ?? 0}</strong>
            </div>
            <div className="stat-card">
              <span className="muted">Members</span>
              <strong>{members.length}</strong>
            </div>
          </section>

          <div className="grid-2">
            <section className="card">
              <h2>Organizations</h2>
              <ul className="org-list">
                {orgs.map((org) => (
                  <li key={org.id}>
                    <button
                      type="button"
                      className={`org-pill ${selectedOrg === org.slug ? "active" : ""}`}
                      onClick={() => setSelectedOrg(org.slug)}
                    >
                      {org.name}
                      <span className="muted"> · {org.my_role}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <form className="form-row compact" onSubmit={createOrg}>
                <label>
                  New organization
                  <input value={orgName} onChange={(e) => setOrgName(e.target.value)} required />
                </label>
                <button type="submit" className="btn btn-primary" disabled={busy === "create"}>
                  {busy === "create" ? "Creating…" : "Create"}
                </button>
              </form>
            </section>

            <section className="card">
              <h2>Invite member</h2>
              <p className="muted">
                Existing users are added immediately. New users get a register link by email (or copy below).
              </p>
              {inviteNotice && <div className="alert">{inviteNotice}</div>}
              {!canAdmin && selectedOrg && (
                <p className="muted">Admin or owner role required to invite members.</p>
              )}
              <form className="form-row" onSubmit={inviteMember}>
                <label>
                  Email
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    required
                    disabled={!canAdmin}
                  />
                </label>
                <label>
                  Role
                  <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} disabled={!canAdmin}>
                    {ROLES.filter((r) => r !== "owner").map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="submit" className="btn btn-secondary" disabled={busy === "invite" || !canAdmin}>
                  {busy === "invite" ? "Inviting…" : "Invite"}
                </button>
              </form>
            </section>
          </div>

          {selectedOrg && (
            <section className="card">
              <h2>Members — {selectedOrg}</h2>
              {loading ? (
                <p className="muted">Loading members…</p>
              ) : members.length === 0 ? (
                <p className="muted">No members loaded.</p>
              ) : (
                <table className="members-table">
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Joined</th>
                      {canAdmin && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((m) => (
                      <tr key={m.id}>
                        <td>{m.email}</td>
                        <td>
                          {canAdmin ? (
                            <select
                              value={m.role}
                              disabled={!!busy}
                              onChange={(e) => changeRole(m.id, e.target.value)}
                            >
                              {ROLES.map((r) => (
                                <option key={r} value={r}>
                                  {r}
                                </option>
                              ))}
                            </select>
                          ) : (
                            m.role
                          )}
                        </td>
                        <td className="muted">{new Date(m.invited_at).toLocaleDateString()}</td>
                        {canAdmin && (
                          <td>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              disabled={!!busy || m.role === "owner"}
                              onClick={() => removeMember(m.id)}
                            >
                              Remove
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {canAdmin && selectedOrg && pendingInvites.length > 0 && (
            <section className="card">
              <h2>Pending invites — {selectedOrg}</h2>
              <ul className="rec-list">
                {pendingInvites.map((inv) => (
                  <li key={inv.id} className="pending-invite-row">
                    <span>
                      {inv.email} · {inv.role} · expires{" "}
                      {new Date(inv.expires_at).toLocaleDateString()}
                    </span>
                    <span className="option-row compact">
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => copyInviteLink(inv.invite_url)}
                      >
                        Copy link
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={!!busy}
                        onClick={() => revokeInvite(inv.id)}
                      >
                        Revoke
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {canAdmin && selectedOrg && (
            <section className="card">
              <h2>GitHub App</h2>
              <p className="muted">
                Install the app on your org or account for PR readiness checks. Requires{" "}
                <code>GITHUB_APP_SLUG</code> and <code>GITHUB_APP_*</code> on the server.
              </p>
              <div className="form-row compact">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy === "github-install"}
                  onClick={installGithubApp}
                >
                  {busy === "github-install" ? "Redirecting…" : "Install GitHub App"}
                </button>
                {selected?.github_installation_id ? (
                  <span className="muted">
                    Linked: installation {selected.github_installation_id}
                    {selected.github_account ? ` · ${selected.github_account}` : ""}
                  </span>
                ) : null}
              </div>
              <p className="muted">Or link manually if OAuth install is not configured:</p>
              <form className="form-row compact" onSubmit={linkGithub}>
                <label>
                  Installation ID
                  <input
                    value={githubInstallId}
                    onChange={(e) => setGithubInstallId(e.target.value)}
                    placeholder="12345678"
                  />
                </label>
                <label>
                  GitHub account
                  <input
                    value={githubAccount}
                    onChange={(e) => setGithubAccount(e.target.value)}
                    placeholder="your-org"
                  />
                </label>
                <button type="submit" className="btn btn-secondary" disabled={busy === "github"}>
                  {busy === "github" ? "Saving…" : "Link installation"}
                </button>
              </form>
              <p className="muted vault-hint">
                Webhook URL: <code>/api/v1/webhooks/github/</code>
              </p>
            </section>
          )}

          <section className="card">
            <h2>Org projects{selectedOrg ? ` — ${selectedOrg}` : ""}</h2>
            {orgProjects.length === 0 ? (
              <p className="muted">
                No projects assigned yet. Assign in{" "}
                <Link to="/">project settings</Link> → Organization.
              </p>
            ) : (
              <ul className="project-grid">
                {orgProjects.map((p) => (
                  <li key={p.id}>
                    <Link to={`/projects/${p.slug}`} className="project-card">
                      <strong>{p.name}</strong>
                      <span className="muted">{p.framework}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
      </>
    </div>
  );
}
