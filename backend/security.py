"""Fernet encryption helpers for per-user secrets."""

import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from backend.config import get_api_settings


def _fernet() -> Fernet:
    settings = get_api_settings()
    raw = settings.api_fernet_key or settings.api_secret_key
    # Derive a stable 32-byte url-safe key from the secret
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_text(value: str) -> str:
    if value is None:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Could not decrypt stored secret — check API_FERNET_KEY / API_SECRET_KEY") from e


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}…{value[-4:]}"
