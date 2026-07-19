import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import SecretField from "../components/SecretField.jsx";

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
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState(location.state?.resetOk ? "Password updated. Sign in with your new password." : "");
  const [busy, setBusy] = useState(false);

  if (isAuthenticated) return <Navigate to="/" replace />;

  function switchMode(next) {
    setMode(next);
    setError("");
    setInfo("");
    setPassword("");
    setConfirmPassword("");
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setInfo("");

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
      if (mode === "login") {
        await login(email, password, rememberMe);
      } else {
        await register(email, password, name || undefined, rememberMe);
        navigate(`/verify-email?email=${encodeURIComponent(email.trim().toLowerCase())}`, {
          replace: true,
          state: { rememberMe },
        });
      }
    } catch (err) {
      if (err.code === "email_not_verified") {
        navigate(`/verify-email?email=${encodeURIComponent(err.email || email.trim().toLowerCase())}`, {
          replace: true,
          state: { rememberMe },
        });
        return;
      }
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
          <p>{mode === "login" ? "Continue to your sync desk." : "Start with email — verify, then add tokens."}</p>
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
          <SecretField
            label="Password"
            value={password}
            required
            minLength={8}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            onChange={(e) => setPassword(e.target.value)}
          />
          {mode === "register" && (
            <>
              <SecretField
                label="Confirm password"
                value={confirmPassword}
                required
                minLength={8}
                autoComplete="new-password"
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              <p className="fineprint">
                Use at least 8 characters with 1 uppercase letter, 1 number, and 1 special character.
              </p>
            </>
          )}
          {mode === "login" && (
            <div className="login-meta-row">
              <label className="remember-row compact">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <span>
                  <strong>Keep me signed in</strong>
                </span>
              </label>
              <Link className="link-quiet" to="/forgot-password">
                Forgot password?
              </Link>
            </div>
          )}
          {mode === "register" && (
            <label className="remember-row">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />
              <span>
                <strong>Keep me signed in</strong>
                <em>After you verify email, stay logged in on this device.</em>
              </span>
            </label>
          )}
          {error && <p className="banner-error">{error}</p>}
          {info && <p className="banner-ok">{info}</p>}
          <button type="submit" className="btn-primary wide" disabled={busy}>
            {busy ? "Working…" : mode === "login" ? "Enter CommitFlow" : "Create account"}
          </button>
        </form>

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
