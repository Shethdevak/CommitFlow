import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
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

export default function ForgotPasswordPage() {
  const { isAuthenticated, forgotPassword, resetPassword } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState("request"); // request | reset
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function onRequest(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      const meta = await forgotPassword(email.trim());
      setInfo("If that email has an account, we sent a reset code.");
      setCooldown(meta?.resend_after_seconds || 60);
      setStep("reset");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onReset(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    if (!isStrongPassword(password)) {
      setError(PASSWORD_RULE);
      return;
    }
    if (password !== confirmPassword) {
      setError("Password and confirm password do not match.");
      return;
    }
    setBusy(true);
    try {
      await resetPassword(email.trim(), code.trim(), password);
      navigate("/login", { replace: true, state: { resetOk: true } });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    setError("");
    setInfo("");
    setBusy(true);
    try {
      const meta = await forgotPassword(email.trim());
      setInfo("If that email has an account, we sent a new code.");
      setCooldown(meta?.resend_after_seconds || 60);
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
          Reset access
          <br />
          <em>with a one-time code.</em>
        </h1>
        <p className="login-copy">
          We’ll email a short code to the address on your account, then you choose a new password.
        </p>
      </section>

      <section className="login-panel reveal delay">
        <div className="panel-head">
          <h2>{step === "request" ? "Forgot password" : "Set new password"}</h2>
          <p>
            {step === "request"
              ? "Enter the email you used to register."
              : "Enter the code from your email and a new password."}
          </p>
        </div>

        {step === "request" ? (
          <form onSubmit={onRequest} className="form-stack">
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </label>
            {error && <p className="banner-error">{error}</p>}
            {info && <p className="banner-ok">{info}</p>}
            <button type="submit" className="btn-primary wide" disabled={busy}>
              {busy ? "Sending…" : "Send reset code"}
            </button>
          </form>
        ) : (
          <form onSubmit={onReset} className="form-stack">
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </label>
            <label className="field">
              <span>Reset code</span>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                required
                minLength={4}
                maxLength={8}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
                placeholder="••••••"
                autoComplete="one-time-code"
                className="otp-input"
              />
            </label>
            <SecretField
              label="New password"
              value={password}
              required
              minLength={8}
              autoComplete="new-password"
              onChange={(e) => setPassword(e.target.value)}
            />
            <SecretField
              label="Confirm new password"
              value={confirmPassword}
              required
              minLength={8}
              autoComplete="new-password"
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
            <p className="fineprint">{PASSWORD_RULE}</p>
            {error && <p className="banner-error">{error}</p>}
            {info && <p className="banner-ok">{info}</p>}
            <button type="submit" className="btn-primary wide" disabled={busy}>
              {busy ? "Updating…" : "Update password"}
            </button>
            <button
              type="button"
              className="btn-secondary wide"
              disabled={busy || cooldown > 0}
              onClick={onResend}
            >
              {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
            </button>
          </form>
        )}

        <Link className="text-switch" to="/login">
          Back to sign in
        </Link>
      </section>
    </div>
  );
}
