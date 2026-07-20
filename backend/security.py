"""Fernet encryption helpers for per-user secrets.

Secrets are encrypted with API_FERNET_KEY (preferred) or API_SECRET_KEY.
Decrypt tries the primary key first, then API_FERNET_LEGACY_SECRETS / prior secrets
so rotating API_SECRET_KEY does not permanently break stored tokens.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

from backend.config import get_api_settings


def _key_from_secret(raw: str) -> bytes:
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _candidate_secrets() -> list[str]:
    """Ordered secrets used to derive Fernet keys (first = encrypt/primary)."""
    settings = get_api_settings()
    ordered: list[str] = []

    def add(value: Optional[str]) -> None:
        v = (value or "").strip()
        if v and v not in ordered:
            ordered.append(v)

    add(settings.api_fernet_key)
    add(settings.api_secret_key)
    for part in (settings.api_fernet_legacy_secrets or "").split(","):
        add(part)
    return ordered


@lru_cache(maxsize=16)
def _fernet_for_secret(raw: str) -> Fernet:
    return Fernet(_key_from_secret(raw))


def _primary_fernet() -> Fernet:
    secrets = _candidate_secrets()
    if not secrets:
        raise RuntimeError("API_SECRET_KEY (or API_FERNET_KEY) must be set")
    return _fernet_for_secret(secrets[0])


def encrypt_text(value: str) -> str:
    if value is None:
        return ""
    return _primary_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    """Decrypt using primary + legacy keys. Raises ValueError if none work."""
    plain, _ = decrypt_text_ex(token)
    return plain


def decrypt_text_ex(token: str) -> Tuple[str, bool]:
    """Return (plaintext, used_legacy_key). used_legacy_key True → caller should re-encrypt."""
    if not token:
        return "", False

    secrets = _candidate_secrets()
    if not secrets:
        raise ValueError("Could not decrypt stored secret — check API_FERNET_KEY / API_SECRET_KEY")

    raw = token.encode("utf-8")
    last_err: Optional[Exception] = None
    for i, secret in enumerate(secrets):
        try:
            plain = _fernet_for_secret(secret).decrypt(raw).decode("utf-8")
            return plain, i > 0
        except InvalidToken as e:
            last_err = e
            continue

    raise ValueError(
        "Could not decrypt stored secret — check API_FERNET_KEY / API_SECRET_KEY "
        "(key was likely rotated; re-save tokens in Integrations, or set API_FERNET_LEGACY_SECRETS)"
    ) from last_err


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}…{value[-4:]}"


def clear_fernet_cache() -> None:
    """For tests — settings changes need a fresh key cache."""
    _fernet_for_secret.cache_clear()
