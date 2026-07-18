import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

const PASSWORD_RULE =
  "Password must be at least 8 characters and include 1 uppercase letter, 1 number, and 1 special character";

function isStrongPassword(password) {
  return (
    password.length >= 8 &&
    /[A-Z]/.test(password) &&
    /[0-9]/.test(password) &&
    /[^A-Za-z0-9]/.test(password)
  );
}

export default function LoginPage() {
  const { isAuthenticated, login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (isAuthenticated) return <Navigate to="/" replace />;

  const apiBase = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
  const githubLoginUrl = `${apiBase}/api/auth/github/login`;

  function switchMode(next) {
    setMode(next);
    setError("");
    setPassword("");
    setConfirmPassword("");
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError("");

    if (mode === "register") {
      if (!isStrongPassword(password)) {
        setError(PASSWORD_RULE);
        return;
      }
      if (password !== confirmPassword) {
        setError("Password and confirm password do not match.");
        return;
      }
    }

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
    <div className="login-stage">
      <div className="login-mesh" aria-hidden="true" />
      <section className="login-hero reveal">
        <img
          src="/logo.png"
          alt="CommitFlow — git to redmine, automated"
          className="brand-logo login-logo"
        />
        <h1>
          Turn today’s commits
          <br />
          <em>into credible hours.</em>
        </h1>
        <p className="login-copy">
          Connect GitHub, GitLab, and Redmine once. Preview weighted to-dos, then write an 8-hour
          day that still looks like real engineering work.
        </p>
        <ul className="login-points">
          <li>Skips merge noise</li>
          <li>Weights big features vs quick fixes</li>
          <li>Dry-run before Redmine write</li>
        </ul>
      </section>

      <section className="login-panel reveal delay">
        <div className="panel-head">
          <h2>{mode === "login" ? "Sign in" : "Create account"}</h2>
          <p>{mode === "login" ? "Continue to your sync desk." : "Start with email — add tokens next."}</p>
        </div>

        <form onSubmit={onSubmit} className="form-stack">
          {mode === "register" && (
            <label className="field">
              <span>Display name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Devak" />
            </label>
          )}
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {mode === "register" && (
            <>
              <label className="field">
                <span>Confirm password</span>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                />
              </label>
              <p className="fineprint">
                Use at least 8 characters with 1 uppercase letter, 1 number, and 1 special character.
              </p>
            </>
          )}
          {error && <p className="banner-error">{error}</p>}
          <button type="submit" className="btn-primary wide" disabled={busy}>
            {busy ? "Working…" : mode === "login" ? "Enter CommitFlow" : "Create account"}
          </button>
        </form>

        <div className="or-row">
          <span>or</span>
        </div>
        <a className="btn-secondary wide" href={githubLoginUrl}>
          Continue with GitHub
        </a>
        <p className="fineprint">GitHub login needs OAuth keys on the server. Email always works.</p>

        <button
          type="button"
          className="text-switch"
          onClick={() => switchMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "New here? Create an account" : "Already set up? Sign in"}
        </button>
      </section>
    </div>
  );
}
