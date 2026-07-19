"""Outbound email via SMTP (Gmail or custom)."""

from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Optional

from loguru import logger

from api.config import get_api_settings


def _parse_from(raw: str) -> tuple[str, str]:
    """Return (display_name, email) from 'Name <email>' or bare email."""
    name, addr = parseaddr(raw)
    if not addr and "@" in raw:
        return "", raw.strip()
    return name, addr


def send_email(*, to: str, subject: str, text: str, html: Optional[str] = None) -> None:
    settings = get_api_settings()
    if not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError(
            "Email is not configured. Set SMTP_USER and SMTP_PASSWORD "
            "(and EMAIL_FROM) on the API service."
        )

    from_name, from_addr = _parse_from(settings.email_from)
    if not from_addr:
        from_addr = settings.smtp_user
    if not from_name:
        from_name = "CommitFlow"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_addr))
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    host = settings.smtp_host
    port = int(settings.smtp_port)
    user = settings.smtp_user
    password = settings.smtp_password.replace(" ", "")

    try:
        if settings.smtp_use_ssl or port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as server:
                server.login(user, password)
                server.sendmail(from_addr, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if settings.smtp_use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(user, password)
                server.sendmail(from_addr, [to], msg.as_string())
    except smtplib.SMTPException as e:
        logger.error("SMTP email failed: {}", e)
        raise RuntimeError(f"Failed to send email: {e}") from e
    except OSError as e:
        logger.error("SMTP connection failed: {}", e)
        raise RuntimeError(f"Failed to connect to mail server: {e}") from e
