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

const STEP_COPY = {
  email: {
    title: "Forgot password",
    subtitle: "Enter the email on your CommitFlow account.",
  },
  code: {
    title: "Enter reset code",
    subtitle: "We sent a 6-digit code to your email. Enter it to continue.",
  },
  password: {
    title: "Set new password",
    subtitle: "Choose a new password for your account.",
  },
};

export default function ForgotPasswordPage() {
  const { isAuthenticated, forgotPassword, verifyResetCode, resetPassword } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState("email"); // email | code | password
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [resetToken, setResetToken] = useState("");
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

  const copy = STEP_COPY[step];

  async function onSubmitEmail(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      const meta = await forgotPassword(email.trim());
      setInfo(`Code sent to ${meta.email}.`);
      setCooldown(meta?.resend_after_seconds || 60);
      setCode("");
      setStep("code");
    } catch (err) {
      // Stay on email step — e.g. account does not exist
      setError(err.message || "No account found for that email.");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmitCode(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      const data = await verifyResetCode(email.trim(), code.trim());
      setResetToken(data.reset_token);
      setPassword("");
      setConfirmPassword("");
      setInfo("");
      setStep("password");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function onSubmitPassword(e) {
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
      await resetPassword(resetToken, password);
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
      setInfo("A new code was sent to your email.");
      setCooldown(meta?.resend_after_seconds || 60);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function goBack() {
    setError("");
    setInfo("");
    if (step === "code") {
      setCode("");
      setStep("email");
    } else if (step === "password") {
      setResetToken("");
      setPassword("");
      setConfirmPassword("");
      setStep("code");
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
          <em>one step at a time.</em>
        </h1>
        <p className="login-copy">
          Confirm your email, enter the code we send, then choose a new password.
        </p>
      </section>

      <section className="login-panel reveal delay">
        <div className="panel-head">
          <p className="step-indicator" aria-hidden="true">
            Step {step === "email" ? "1" : step === "code" ? "2" : "3"} of 3
          </p>
          <h2>{copy.title}</h2>
          <p>{copy.subtitle}</p>
        </div>

        {step === "email" && (
          <form onSubmit={onSubmitEmail} className="form-stack">
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                autoFocus
              />
            </label>
            {error && <p className="banner-error">{error}</p>}
            <button type="submit" className="btn-primary wide" disabled={busy}>
              {busy ? "Checking…" : "Continue"}
            </button>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={onSubmitCode} className="form-stack">
            <p className="fineprint">
              Code sent to <strong>{email}</strong>
            </p>
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
                autoFocus
              />
            </label>
            {error && <p className="banner-error">{error}</p>}
            {info && <p className="banner-ok">{info}</p>}
            <button type="submit" className="btn-primary wide" disabled={busy || code.length < 4}>
              {busy ? "Checking…" : "Verify code"}
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

        {step === "password" && (
          <form onSubmit={onSubmitPassword} className="form-stack">
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
            <button type="submit" className="btn-primary wide" disabled={busy}>
              {busy ? "Updating…" : "Update password"}
            </button>
          </form>
        )}

        <div className="auth-footer">
          {step === "code" && (
            <button type="button" className="text-switch" onClick={goBack}>
              Use a different email
            </button>
          )}
          {step === "password" && (
            <button type="button" className="text-switch" onClick={goBack}>
              Back to code
            </button>
          )}
          <Link className="text-switch" to="/login">
            ← Back to sign in
          </Link>
        </div>
      </section>
    </div>
  );
}
