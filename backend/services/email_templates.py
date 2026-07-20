"""Branded HTML email templates for CommitFlow OTP mail."""

from __future__ import annotations

from html import escape

from backend.config import get_api_settings

# Match web/src/styles.css
INK = "#14181c"
INK_SOFT = "#3a434d"
MUTED = "#6b7580"
PAPER = "#f6f3ee"
PANEL = "#fffcf7"
TEAL = "#1f6f63"
ACCENT = "#c45c26"
LINE = "#e4dfd6"


def _logo_url() -> str:
    settings = get_api_settings()
    base = (settings.api_frontend_url or "").rstrip("/")
    if not base:
        return ""
    return f"{base}/commitflow-icon.png"


def build_otp_email(
    *,
    code: str,
    purpose: str,
    expire_minutes: int,
) -> tuple[str, str, str]:
    """Return (subject, text, html) for an OTP message."""
    if purpose == "signup":
        subject = "Verify your CommitFlow email"
        headline = "Confirm your email"
        blurb = "Enter this code in CommitFlow to finish creating your account."
    elif purpose == "email_change":
        subject = "Confirm your new CommitFlow email"
        headline = "Confirm your new email"
        blurb = "Enter this code in CommitFlow to finish updating the email on your account."
    else:
        subject = "Reset your CommitFlow password"
        headline = "Reset your password"
        blurb = "Enter this code in CommitFlow to choose a new password."

    safe_code = escape(code)
    safe_blurb = escape(blurb)
    safe_headline = escape(headline)
    logo = _logo_url()
    logo_block = ""
    if logo:
        logo_block = f"""
          <tr>
            <td style="padding:0 0 24px 0;text-align:center;">
              <img src="{escape(logo)}" width="56" height="56" alt="CommitFlow"
                   style="display:block;margin:0 auto;border:0;border-radius:14px;" />
            </td>
          </tr>
        """

    text = (
        f"CommitFlow — {headline}\n\n"
        f"{blurb}\n\n"
        f"  {code}\n\n"
        f"This code expires in {expire_minutes} minutes.\n"
        f"If you did not request this, you can ignore this email.\n"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background:{PAPER};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background:{PAPER};padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
               style="max-width:480px;background:{PANEL};border:1px solid {LINE};border-radius:20px;
                      overflow:hidden;box-shadow:0 18px 40px rgba(20,24,28,0.08);">
          <tr>
            <td style="height:4px;background:linear-gradient(90deg,{TEAL},{ACCENT});font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td style="padding:36px 32px 40px 32px;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{INK};">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                {logo_block}
                <tr>
                  <td style="padding:0 0 8px 0;text-align:center;">
                    <p style="margin:0;font-size:12px;letter-spacing:0.12em;text-transform:uppercase;
                              color:{TEAL};font-weight:700;">CommitFlow</p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 0 12px 0;text-align:center;">
                    <h1 style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:26px;
                               font-weight:600;letter-spacing:-0.02em;color:{INK};">{safe_headline}</h1>
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 0 28px 0;text-align:center;">
                    <p style="margin:0;font-size:15px;line-height:1.55;color:{INK_SOFT};">{safe_blurb}</p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 0 28px 0;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                           style="background:{PAPER};border:1px solid {LINE};border-radius:14px;">
                      <tr>
                        <td style="padding:22px 16px;text-align:center;">
                          <p style="margin:0 0 8px 0;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;
                                    color:{MUTED};font-weight:600;">Verification code</p>
                          <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:34px;
                                    letter-spacing:0.28em;font-weight:700;color:{INK};">{safe_code}</p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="text-align:center;">
                    <p style="margin:0;font-size:13px;line-height:1.5;color:{MUTED};">
                      Expires in {int(expire_minutes)} minutes. If you did not request this, ignore this email.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
        <p style="margin:20px 0 0 0;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                  font-size:12px;color:{MUTED};text-align:center;">
          Git commits → Redmine, automated
        </p>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return subject, text, html
