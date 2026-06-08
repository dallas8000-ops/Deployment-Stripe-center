import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import AgencyPage from "./pages/AgencyPage";
import GithubCallbackPage from "./pages/GithubCallbackPage";
import BillingPage from "./pages/BillingPage";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import ProjectPage from "./pages/ProjectPage";
import ProjectSettingsPage from "./pages/ProjectSettingsPage";
import RegisterPage from "./pages/RegisterPage";

function ProtectedRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="page-center">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function PublicOnlyRoute() {
  const { user, loading } = useAuth();
  if (loading) return <div className="page-center">Loading…</div>;
  if (user) return <Navigate to="/" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<PublicOnlyRoute />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="agency" element={<AgencyPage />} />
          <Route path="agency/github/callback" element={<GithubCallbackPage />} />
          <Route path="projects/:slug" element={<ProjectPage />} />
          <Route path="projects/:slug/settings" element={<ProjectSettingsPage />} />
          <Route path="billing" element={<BillingPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
