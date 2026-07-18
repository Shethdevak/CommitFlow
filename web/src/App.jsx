import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import SyncPage from "./pages/SyncPage.jsx";
import AuthCallback from "./pages/AuthCallback.jsx";

function Shell({ children }) {
  const { user, logout } = useAuth();
  const label = user?.display_name || user?.email || user?.github_login || "Account";

  return (
    <div className="app-frame">
      <div className="app-aura" aria-hidden="true" />
      <aside className="rail">
        <NavLink to="/" end className="rail-brand" aria-label="CommitFlow home">
          <img
            src="/logo.png"
            alt="CommitFlow — git to redmine, automated"
            className="brand-logo rail-logo"
          />
        </NavLink>

        <nav className="rail-nav">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
            <span className="nav-ico" aria-hidden="true">
              ◇
            </span>
            Sync desk
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}>
            <span className="nav-ico" aria-hidden="true">
              ▤
            </span>
            Integrations
          </NavLink>
        </nav>

        <div className="rail-foot">
          <div className="who">
            <span className="avatar">{label.slice(0, 1).toUpperCase()}</span>
            <div>
              <p className="who-name">{label}</p>
              <p className="who-meta">Signed in</p>
            </div>
          </div>
          <button type="button" className="btn-quiet" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      <div className="workspace">
        <header className="workspace-top">
          <p className="workspace-kicker">Worklog automation</p>
          <p className="workspace-hint">Preview first. Commit when the hours look right.</p>
        </header>
        <main className="workspace-main">{children}</main>
      </div>
    </div>
  );
}

function Private({ children }) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) {
    return (
      <div className="boot">
        <div className="boot-pulse" />
        <p>Opening CommitFlow…</p>
      </div>
    );
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;
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
