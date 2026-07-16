import { useState } from "react";
import { Navigate, Link } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function LoginPage() {
  const { token, login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (token) return <Navigate to="/" replace />;

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password, name || undefined);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <p className="eyebrow">CommitFlow</p>
        <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p className="lede">Connect Git + Redmine once. Sync worklogs any day.</p>

        <form onSubmit={onSubmit} className="stack">
          {mode === "register" && (
            <label>
              Display name
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Devak" />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
          </button>
        </form>

        <div className="divider">or</div>
        <a className="github-btn" href="http://localhost:8000/api/auth/github/login">
          Continue with GitHub
        </a>
        <p className="muted tiny">GitHub login needs server OAuth keys. Email signup always works.</p>

        <button type="button" className="linkish" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need an account? Sign up" : "Have an account? Log in"}
        </button>
      </div>
    </div>
  );
}
