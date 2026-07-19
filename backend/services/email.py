"""Outbound email — Gmail SMTP or HTTPS mail bridge.

Many PaaS hosts (Render, Railway, etc.) block/time out smtp.gmail.com.
To keep a Gmail App Password in production, deploy tools/gmail_mail_bridge on a
small VPS that allows SMTP, then set EMAIL_PROVIDER=bridge + MAIL_BRIDGE_*.
"""

from __future__ import annotations

import smtplib
import socket
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Optional

import requests
from loguru import logger

from api.config import get_api_settings


def _parse_from(raw: str) -> tuple[str, str]:
    name, addr = parseaddr(raw)
    if not addr and "@" in raw:
        return "", raw.strip()
    return name, addr


def send_email(*, to: str, subject: str, text: str, html: Optional[str] = None) -> None:
    settings = get_api_settings()
    provider = (settings.email_provider or "auto").strip().lower()

    if provider == "auto":
        if settings.mail_bridge_url:
            provider = "bridge"
        elif settings.smtp_user and settings.smtp_password:
            provider = "smtp"
        elif settings.resend_api_key:
            provider = "resend"
        else:
            raise RuntimeError(
                "Email is not configured. Set SMTP_USER + SMTP_PASSWORD (local), "
                "or MAIL_BRIDGE_URL + MAIL_BRIDGE_SECRET (Render → Gmail bridge)."
            )

    if provider == "bridge":
        _send_via_bridge(to=to, subject=subject, text=text, html=html)
        return
    if provider == "smtp":
        _send_via_smtp(to=to, subject=subject, text=text, html=html)
        return
    if provider == "resend":
        _send_via_resend(to=to, subject=subject, text=text, html=html)
        return

    raise RuntimeError(
        f"Unknown EMAIL_PROVIDER '{settings.email_provider}'. Use auto, smtp, bridge, or resend."
    )


def _send_via_bridge(*, to: str, subject: str, text: str, html: Optional[str]) -> None:
    """HTTPS call to a small worker that sends with your Gmail App Password."""
    settings = get_api_settings()
    if not settings.mail_bridge_url or not settings.mail_bridge_secret:
        raise RuntimeError(
            "Mail bridge not configured. Set MAIL_BRIDGE_URL and MAIL_BRIDGE_SECRET on Render. "
            "Deploy tools/gmail_mail_bridge with your Gmail SMTP_USER / SMTP_PASSWORD."
        )

    url = settings.mail_bridge_url.rstrip("/") + "/send"
    try:
        res = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.mail_bridge_secret}",
                "Content-Type": "application/json",
            },
            json={"to": to, "subject": subject, "text": text, "html": html},
            timeout=30,
        )
    except requests.RequestException as e:
        logger.error("Mail bridge request failed: {}", e)
        raise RuntimeError(f"Failed to reach mail bridge: {e}") from e

    if not res.ok:
        detail = res.text[:300]
        logger.error("Mail bridge failed: {} {}", res.status_code, detail)
        raise RuntimeError(f"Mail bridge error ({res.status_code}): {detail}")


def _send_via_resend(*, to: str, subject: str, text: str, html: Optional[str]) -> None:
    settings = get_api_settings()
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not set.")

    payload = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html

    try:
        res = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
    except requests.RequestException as e:
        logger.error("Resend request failed: {}", e)
        raise RuntimeError(f"Failed to reach Resend: {e}") from e

    if not res.ok:
        logger.error("Resend email failed: {} {}", res.status_code, res.text[:300])
        raise RuntimeError(f"Failed to send email ({res.status_code})")


def _smtp_connect(host: str, port: int, *, use_ssl: bool, timeout: int = 30):
    last_err: Optional[OSError] = None
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise OSError(f"DNS lookup failed for {host}: {e}") from e

    context = ssl.create_default_context()
    for family, socktype, proto, _canon, sockaddr in infos:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            if use_ssl:
                sock = context.wrap_socket(sock, server_hostname=host)
                server = smtplib.SMTP_SSL()
                server.sock = sock
                server._host = host
                (code, msg) = server.getreply()
                if code != 220:
                    raise smtplib.SMTPConnectError(code, msg)
                return server
            server = smtplib.SMTP()
            server.sock = sock
            server._host = host
            (code, msg) = server.getreply()
            if code != 220:
                raise smtplib.SMTPConnectError(code, msg)
            return server
        except OSError as e:
            last_err = e
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            continue

    raise OSError(last_err or f"Could not connect to {host}:{port}")


def build_mime_message(
    *,
    from_header: str,
    to: str,
    subject: str,
    text: str,
    html: Optional[str] = None,
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_header
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def send_smtp_message(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to: str,
    raw_message: str,
    use_tls: bool = True,
    use_ssl: bool = False,
    timeout: int = 20,
) -> None:
    password = password.replace(" ", "")
    use_ssl = bool(use_ssl or port == 465)
    server = _smtp_connect(host, port, use_ssl=use_ssl, timeout=timeout)
    try:
        server.ehlo()
        if not use_ssl and use_tls:
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()
        server.login(user, password)
        server.sendmail(from_addr, [to], raw_message)
    finally:
        try:
            server.quit()
        except Exception:
            server.close()


def _send_via_smtp(*, to: str, subject: str, text: str, html: Optional[str]) -> None:
    settings = get_api_settings()
    if not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError(
            "Set SMTP_USER and SMTP_PASSWORD (Gmail address + App Password) on the API host."
        )

    from_name, from_addr = _parse_from(settings.email_from)
    if not from_addr:
        from_addr = settings.smtp_user
    if not from_name:
        from_name = "CommitFlow"

    msg = build_mime_message(
        from_header=formataddr((from_name, from_addr)),
        to=to,
        subject=subject,
        text=text,
        html=html,
    )
    raw = msg.as_string()
    user = settings.smtp_user
    password = settings.smtp_password
    host = settings.smtp_host

    # Prefer configured port; fall back to the other Gmail port on connect failure.
    primary = (int(settings.smtp_port), bool(settings.smtp_use_ssl or int(settings.smtp_port) == 465), settings.smtp_use_tls)
    fallback = (465, True, False) if primary[0] != 465 else (587, False, True)
    attempts = [primary, fallback]
    last_err: Optional[Exception] = None

    for port, use_ssl, use_tls in attempts:
        try:
            send_smtp_message(
                host=host,
                port=port,
                user=user,
                password=password,
                from_addr=from_addr,
                to=to,
                raw_message=raw,
                use_tls=use_tls,
                use_ssl=use_ssl,
            )
            return
        except (smtplib.SMTPException, OSError, TimeoutError) as e:
            last_err = e
            logger.warning("SMTP via {}:{} failed: {}", host, port, e)

    logger.error("SMTP connection failed after retries: {}", last_err)
    raise RuntimeError(
        "Cannot reach Gmail SMTP from this server (timed out / blocked). "
        "Render and Railway both block smtp.gmail.com. "
        "Keep using your Gmail App Password via tools/gmail_mail_bridge on a small VPS, "
        "then set EMAIL_PROVIDER=bridge, MAIL_BRIDGE_URL, and MAIL_BRIDGE_SECRET on the API. "
        f"({last_err})"
    ) from last_err
