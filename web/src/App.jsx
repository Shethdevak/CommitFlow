import { Navigate, Route, Routes, Link, useNavigate } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import SyncPage from "./pages/SyncPage.jsx";
import AuthCallback from "./pages/AuthCallback.jsx";

function Shell({ children }) {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          CommitFlow
        </Link>
        <nav>
          <Link to="/">Sync</Link>
          <Link to="/settings">Settings</Link>
        </nav>
        <div className="userbox">
          <span>{user?.display_name || user?.email || user?.github_login}</span>
          <button type="button" className="ghost" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}

function Private({ children }) {
  const { token, loading } = useAuth();
  if (loading) return <div className="center">Loading…</div>;
  if (!token) return <Navigate to="/login" replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route
        path="/"
        element={
          <Private>
            <SyncPage />
          </Private>
        }
      />
      <Route
        path="/settings"
        element={
          <Private>
            <SettingsPage />
          </Private>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
