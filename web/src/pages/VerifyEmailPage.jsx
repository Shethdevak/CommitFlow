import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function VerifyEmailPage() {
  const { isAuthenticated, verifyEmail, resendSignupOtp } = useAuth();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState(params.get("email") || "");
  const [code, setCode] = useState("");
  const [rememberMe, setRememberMe] = useState(!!location.state?.rememberMe);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [resendBusy, setResendBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      await verifyEmail(email.trim(), code.trim(), rememberMe);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    setError("");
    setInfo("");
    setResendBusy(true);
    try {
      const meta = await resendSignupOtp(email.trim());
      setInfo("A new code was sent to your email.");
      setCooldown(meta?.resend_after_seconds || 60);
    } catch (err) {
      setError(err.message);
    } finally {
      setResendBusy(false);
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
          Check your inbox
          <br />
          <em>for a 6-digit code.</em>
        </h1>
        <p className="login-copy">
          We sent a verification code to confirm your email before you can sync commits to Redmine.
        </p>
      </section>

      <section className="login-panel reveal delay">
        <div className="panel-head">
          <h2>Verify email</h2>
          <p>Enter the code we emailed you. It expires in about 10 minutes.</p>
        </div>

        <form onSubmit={onSubmit} className="form-stack">
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
            <span>Verification code</span>
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
          <label className="remember-row">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
            />
            <span>
              <strong>Keep me signed in</strong>
              <em>After verifying, stay logged in on this device.</em>
            </span>
          </label>
          {error && <p className="banner-error">{error}</p>}
          {info && <p className="banner-ok">{info}</p>}
          <button type="submit" className="btn-primary wide" disabled={busy}>
            {busy ? "Verifying…" : "Verify and continue"}
          </button>
        </form>

        <button
          type="button"
          className="btn-secondary wide"
          disabled={resendBusy || cooldown > 0 || !email.trim()}
          onClick={onResend}
        >
          {cooldown > 0 ? `Resend in ${cooldown}s` : resendBusy ? "Sending…" : "Resend code"}
        </button>

        <Link className="text-switch" to="/login">
          Back to sign in
        </Link>
      </section>
    </div>
  );
}
