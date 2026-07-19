"""OTP create / verify helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.config import get_api_settings
from api.db.models import EmailOtp
from api.services.email import send_email

Purpose = Literal["signup", "reset"]


def _hash_code(email: str, purpose: str, code: str) -> str:
    settings = get_api_settings()
    raw = f"{email.lower()}|{purpose}|{code}|{settings.api_secret_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    settings = get_api_settings()
    length = max(4, min(8, int(settings.otp_length)))
    upper = 10**length
    return str(secrets.randbelow(upper)).zfill(length)


def create_and_send_otp(db: Session, *, email: str, purpose: Purpose) -> dict:
    """Create/replace OTP for email+purpose and send it. Returns public meta."""
    settings = get_api_settings()
    email_l = email.lower().strip()
    now = datetime.utcnow()

    existing = (
        db.query(EmailOtp)
        .filter(EmailOtp.email == email_l, EmailOtp.purpose == purpose)
        .first()
    )
    if existing and existing.last_sent_at:
        elapsed = (now - existing.last_sent_at).total_seconds()
        cooldown = int(settings.otp_resend_cooldown_seconds)
        if elapsed < cooldown:
            wait = int(cooldown - elapsed)
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {wait}s before requesting another code.",
            )

    code = _generate_code()
    code_hash = _hash_code(email_l, purpose, code)
    expires = now + timedelta(minutes=int(settings.otp_expire_minutes))

    if existing:
        existing.code_hash = code_hash
        existing.attempts = 0
        existing.expires_at = expires
        existing.last_sent_at = now
    else:
        db.add(
            EmailOtp(
                email=email_l,
                purpose=purpose,
                code_hash=code_hash,
                attempts=0,
                expires_at=expires,
                last_sent_at=now,
            )
        )
    db.flush()

    if purpose == "signup":
        subject = "Verify your CommitFlow email"
        blurb = "Use this code to verify your CommitFlow account:"
    else:
        subject = "Reset your CommitFlow password"
        blurb = "Use this code to reset your CommitFlow password:"

    text = (
        f"{blurb}\n\n"
        f"  {code}\n\n"
        f"This code expires in {settings.otp_expire_minutes} minutes. "
        f"If you did not request this, you can ignore this email."
    )
    html = f"""
    <div style="font-family:Georgia,serif;max-width:480px;margin:0 auto;color:#14181c">
      <h1 style="font-size:22px">CommitFlow</h1>
      <p>{blurb}</p>
      <p style="font-size:28px;letter-spacing:0.2em;font-weight:700">{code}</p>
      <p style="color:#6b7580;font-size:14px">Expires in {settings.otp_expire_minutes} minutes.</p>
    </div>
    """
    try:
        send_email(to=email_l, subject=subject, text=text, html=html)
    except RuntimeError as e:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(e)) from e

    db.commit()

    return {
        "email": email_l,
        "purpose": purpose,
        "expires_in_seconds": int(settings.otp_expire_minutes) * 60,
        "resend_after_seconds": int(settings.otp_resend_cooldown_seconds),
    }


def verify_otp(db: Session, *, email: str, purpose: Purpose, code: str) -> None:
    settings = get_api_settings()
    email_l = email.lower().strip()
    code = (code or "").strip()
    now = datetime.utcnow()

    row = (
        db.query(EmailOtp)
        .filter(EmailOtp.email == email_l, EmailOtp.purpose == purpose)
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="No verification code found. Request a new one.")

    if row.expires_at < now:
        raise HTTPException(status_code=400, detail="Code expired. Request a new one.")

    if row.attempts >= int(settings.otp_max_attempts):
        raise HTTPException(status_code=400, detail="Too many attempts. Request a new code.")

    expected = _hash_code(email_l, purpose, code)
    if not secrets.compare_digest(expected, row.code_hash):
        row.attempts += 1
        db.commit()
        left = int(settings.otp_max_attempts) - row.attempts
        raise HTTPException(
            status_code=400,
            detail=f"Invalid code. {max(0, left)} attempt(s) left.",
        )

    db.delete(row)
    db.commit()
