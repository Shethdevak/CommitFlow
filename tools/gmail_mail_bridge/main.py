"""
Tiny HTTPS → Gmail SMTP bridge.

Why: Render cannot open smtp.gmail.com. This worker runs on a host that CAN
(Railway, Fly.io, a VPS) and sends with your Gmail App Password.

Env (on the bridge host):
  SMTP_USER=commitflow111@gmail.com
  SMTP_PASSWORD=your_16_char_app_password
  EMAIL_FROM=CommitFlow <commitflow111@gmail.com>
  MAIL_BRIDGE_SECRET=long-random-shared-secret
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587

On Render API, set:
  EMAIL_PROVIDER=bridge
  MAIL_BRIDGE_URL=https://your-bridge.up.railway.app
  MAIL_BRIDGE_SECRET=same-secret-as-above

Run locally:
  uvicorn tools.gmail_mail_bridge.main:app --host 0.0.0.0 --port 8090
"""

from __future__ import annotations

import os
from email.utils import formataddr, parseaddr
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from api.services.email import build_mime_message, send_smtp_message

app = FastAPI(title="CommitFlow Gmail mail bridge", docs_url=None, redoc_url=None)


class SendBody(BaseModel):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    html: Optional[str] = None


def _require_secret(authorization: Optional[str]) -> None:
    expected = os.environ.get("MAIL_BRIDGE_SECRET", "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="MAIL_BRIDGE_SECRET is not set on the bridge")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[len("Bearer ") :].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid bridge secret")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/send")
def send(body: SendBody, authorization: Optional[str] = Header(default=None)):
    _require_secret(authorization)

    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    if not user or not password:
        raise HTTPException(status_code=500, detail="SMTP_USER / SMTP_PASSWORD not set on bridge")

    raw_from = os.environ.get("EMAIL_FROM", f"CommitFlow <{user}>")
    name, from_addr = parseaddr(raw_from)
    if not from_addr:
        from_addr = user
    if not name:
        name = "CommitFlow"

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
    use_ssl = os.environ.get("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")

    msg = build_mime_message(
        from_header=formataddr((name, from_addr)),
        to=body.to,
        subject=body.subject,
        text=body.text,
        html=body.html,
    )

    try:
        send_smtp_message(
            host=host,
            port=port,
            user=user,
            password=password,
            from_addr=from_addr,
            to=body.to,
            raw_message=msg.as_string(),
            use_tls=use_tls,
            use_ssl=use_ssl,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMTP send failed: {e}") from e

    return {"ok": True}
