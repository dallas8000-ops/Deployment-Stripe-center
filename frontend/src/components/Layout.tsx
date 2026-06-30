import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";

import { apiConnectionLabel, projectsApi } from "../api/client";
import { APP_SHORT_NAME } from "../config/branding";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/", label: "Projects", match: (path: string) => path === "/" || path.startsWith("/projects/") },
  { to: "/deploy", label: "Deploy", match: (path: string) => path.startsWith("/deploy") },
  { to: "/agency", label: "Agency", match: (path: string) => path.startsWith("/agency") },
  { to: "/billing", label: "Billing", match: (path: string) => path.startsWith("/billing") },
] as const;

function settingsPath(slug: string | undefined, pathname: string) {
  return slug && pathname.startsWith(`/projects/${slug}`) ? `/projects/${slug}/settings` : null;
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { slug } = useParams();
  const [projectName, setProjectName] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) {
      setProjectName(null);
      return;
    }
    let cancelled = false;
    projectsApi
      .get(slug)
      .then((p) => {
        if (!cancelled) setProjectName(p.name);
      })
      .catch(() => {
        if (!cancelled) setProjectName(slug);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-start">
          <NavLink to="/" className="brand" end>
            <span className="brand-mark" aria-hidden>
              ◆
            </span>
            {APP_SHORT_NAME}
          </NavLink>
          <nav className="topbar-nav" aria-label="Main">
            {NAV.map(({ to, label, match }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={() =>
                  match(location.pathname) ? "topbar-nav-link active" : "topbar-nav-link"
                }
              >
                {label}
              </NavLink>
            ))}
            {settingsPath(slug, location.pathname) && (
              <NavLink
                to={settingsPath(slug, location.pathname)!}
                className={({ isActive }) =>
                  isActive ? "topbar-nav-link active" : "topbar-nav-link"
                }
              >
                Settings
              </NavLink>
            )}
          </nav>
        </div>

        {slug && (
          <div className="topbar-breadcrumb" aria-label="Breadcrumb">
            <NavLink to="/" className="topbar-breadcrumb-link">
              Projects
            </NavLink>
            <span className="topbar-breadcrumb-sep" aria-hidden>
              /
            </span>
            <span className="topbar-breadcrumb-current">{projectName || "…"}</span>
          </div>
        )}

        <div className="topbar-right">
          <span className="muted topbar-env" title="One app: Stripe setup + deploy/transfer (API Transfer is not a separate product)">
            {apiConnectionLabel()}
          </span>
          <span className="user-email" title={user?.email}>
            <Link to="/account/security" className="topbar-nav-link">
              {user?.email}
            </Link>
          </span>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            Log out
          </button>
        </div>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
