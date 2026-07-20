import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth.jsx";
import SecretField from "../components/SecretField.jsx";

const PASSWORD_RULE =
  "At least 8 characters, with 1 uppercase, 1 number, and 1 special character.";

export default function AccountPage() {
  const { user, refreshUser } = useAuth();

  const [displayName, setDisplayName] = useState(user?.display_name || "");
  const [nameBusy, setNameBusy] = useState(false);
  const [nameMsg, setNameMsg] = useState("");
  const [nameError, setNameError] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwMsg, setPwMsg] = useState("");
  const [pwError, setPwError] = useState("");

  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailStep, setEmailStep] = useState("form"); // form | code
  const [emailCode, setEmailCode] = useState("");
  const [emailBusy, setEmailBusy] = useState(false);
  const [emailMsg, setEmailMsg] = useState("");
  const [emailError, setEmailError] = useState("");
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    setDisplayName(user?.display_name || "");
  }, [user?.display_name]);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function saveDisplayName(e) {
    e.preventDefault();
    setNameBusy(true);
    setNameMsg("");
    setNameError("");
    try {
      const updated = await api("/api/auth/account/display-name", {
        method: "PATCH",
        body: { display_name: displayName },
      });
      await refreshUser();
      setDisplayName(updated.display_name || "");
      setNameMsg("Saved.");
    } catch (err) {
      setNameError(err.message);
    } finally {
      setNameBusy(false);
    }
  }

  async function savePassword(e) {
    e.preventDefault();
    setPwBusy(true);
    setPwMsg("");
    setPwError("");
    if (newPassword !== confirmPassword) {
      setPwError("New passwords do not match.");
      setPwBusy(false);
      return;
    }
    try {
      await api("/api/auth/account/password", {
        method: "POST",
        body: {
          current_password: currentPassword,
          new_password: newPassword,
        },
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwMsg("Password updated.");
    } catch (err) {
      setPwError(err.message);
    } finally {
      setPwBusy(false);
    }
  }

  async function requestEmailChange(e) {
    e.preventDefault();
    setEmailBusy(true);
    setEmailError("");
    setEmailMsg("");
    try {
      const meta = await api("/api/auth/account/email/request", {
        method: "POST",
        body: {
          new_email: newEmail.trim(),
          current_password: emailPassword,
        },
      });
      setEmailStep("code");
      setCooldown(meta.resend_after_seconds || 60);
      setEmailMsg(`Code sent to ${meta.email}.`);
    } catch (err) {
      setEmailError(err.message);
    } finally {
      setEmailBusy(false);
    }
  }

  async function resendEmailCode() {
    setEmailBusy(true);
    setEmailError("");
    setEmailMsg("");
    try {
      const meta = await api("/api/auth/account/email/request", {
        method: "POST",
        body: {
          new_email: newEmail.trim(),
          current_password: emailPassword,
        },
      });
      setCooldown(meta.resend_after_seconds || 60);
      setEmailMsg(`Code resent to ${meta.email}.`);
    } catch (err) {
      setEmailError(err.message);
    } finally {
      setEmailBusy(false);
    }
  }

  async function verifyEmailChange(e) {
    e.preventDefault();
    setEmailBusy(true);
    setEmailError("");
    setEmailMsg("");
    try {
      await api("/api/auth/account/email/verify", {
        method: "POST",
        body: {
          new_email: newEmail.trim(),
          code: emailCode,
        },
      });
      await refreshUser();
      setEmailStep("form");
      setNewEmail("");
      setEmailPassword("");
      setEmailCode("");
      setEmailMsg("Email updated and verified.");
    } catch (err) {
      setEmailError(err.message);
    } finally {
      setEmailBusy(false);
    }
  }

  function cancelEmailChange() {
    setEmailStep("form");
    setEmailCode("");
    setEmailError("");
    setEmailMsg("");
  }

  const hasPassword = Boolean(user?.has_password);
  const label = user?.display_name || user?.email || user?.github_login || "Account";

  return (
    <div className="page-block account-page reveal">
      <header className="page-intro">
        <h1>Account</h1>
        <p>Profile, password, and email — email changes need a verification code.</p>
      </header>

      <div className="account-stack">
        <section className="account-panel">
          <div className="account-panel-head">
            <div className="account-identity">
              <span className="account-avatar" aria-hidden="true">
                {label.slice(0, 1).toUpperCase()}
              </span>
              <div>
                <h2>Profile</h2>
                <p>{user?.email || "No email on file"}</p>
              </div>
            </div>
          </div>

          <form className="account-form" onSubmit={saveDisplayName}>
            <div className="account-inline">
              <label className="field account-inline-field">
                <span>Display name</span>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  required
                  maxLength={255}
                  autoComplete="nickname"
                />
              </label>
              <button type="submit" className="btn-primary" disabled={nameBusy}>
                {nameBusy ? "Saving…" : "Save"}
              </button>
            </div>
            {nameMsg && <p className="banner-ok account-flash">{nameMsg}</p>}
            {nameError && <p className="banner-error account-flash">{nameError}</p>}
          </form>
        </section>

        <section className="account-panel">
          <div className="account-panel-head">
            <h2>Password</h2>
            <p>{PASSWORD_RULE}</p>
          </div>

          <form className="account-form account-form-grid account-form-split" onSubmit={savePassword}>
            <SecretField
              label="Current password"
              value={currentPassword}
              required
              autoComplete="current-password"
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
            <SecretField
              label="New password"
              value={newPassword}
              required
              minLength={8}
              autoComplete="new-password"
              onChange={(e) => setNewPassword(e.target.value)}
            />
            <SecretField
              label="Confirm new password"
              value={confirmPassword}
              required
              minLength={8}
              autoComplete="new-password"
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
            <div className="account-actions">
              {pwMsg && <p className="banner-ok">{pwMsg}</p>}
              {pwError && <p className="banner-error">{pwError}</p>}
              {!hasPassword && (
                <p className="fineprint">
                  No password on this account yet. Use forgot password on the sign-in page to set
                  one.
                </p>
              )}
              <button type="submit" className="btn-primary" disabled={pwBusy || !hasPassword}>
                {pwBusy ? "Updating…" : "Update password"}
              </button>
            </div>
          </form>
        </section>

        <section className="account-panel">
          <div className="account-panel-head">
            <h2>Email</h2>
            <p>
              Current <strong>{user?.email || "—"}</strong>. We’ll send a code to the new address
              before switching.
            </p>
          </div>

          {emailStep === "form" ? (
            <form className="account-form account-form-grid" onSubmit={requestEmailChange}>
              <label className="field">
                <span>New email</span>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  autoComplete="email"
                />
              </label>
              <SecretField
                label="Current password"
                value={emailPassword}
                required
                autoComplete="current-password"
                onChange={(e) => setEmailPassword(e.target.value)}
              />
              <div className="account-actions">
                {emailMsg && <p className="banner-ok">{emailMsg}</p>}
                {emailError && <p className="banner-error">{emailError}</p>}
                {!hasPassword && (
                  <p className="fineprint">
                    Email changes need a password. Set one via forgot password first.
                  </p>
                )}
                <button type="submit" className="btn-primary" disabled={emailBusy || !hasPassword}>
                  {emailBusy ? "Sending…" : "Send verification code"}
                </button>
              </div>
            </form>
          ) : (
            <form className="account-form account-form-grid" onSubmit={verifyEmailChange}>
              <label className="field">
                <span>Verification code</span>
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  required
                  minLength={4}
                  maxLength={8}
                  value={emailCode}
                  onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
                  placeholder="••••••"
                  autoComplete="one-time-code"
                  className="otp-input"
                  autoFocus
                />
                <span className="field-hint">Sent to {newEmail.trim()}</span>
              </label>
              <div className="account-actions">
                {emailMsg && <p className="banner-ok">{emailMsg}</p>}
                {emailError && <p className="banner-error">{emailError}</p>}
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={emailBusy || emailCode.length < 4}
                >
                  {emailBusy ? "Verifying…" : "Verify and update email"}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={emailBusy || cooldown > 0}
                  onClick={resendEmailCode}
                >
                  {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
                </button>
                <button type="button" className="text-switch" onClick={cancelEmailChange}>
                  Cancel
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
