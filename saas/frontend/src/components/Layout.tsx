import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          Stripe Installer
        </Link>
        <nav className="topbar-nav">
          <Link to="/">Projects</Link>
          <Link to="/billing">Billing</Link>
        </nav>
        <div className="topbar-right">
          <span className="user-email">{user?.email}</span>
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
