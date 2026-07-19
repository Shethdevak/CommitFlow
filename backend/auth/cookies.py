"""HttpOnly session cookie helpers for JWT auth."""

from fastapi import Response
from api.config import get_api_settings

COOKIE_NAME = "cf_session"


def _cookie_flags(*, remember_me: bool = False) -> dict:
    settings = get_api_settings()
    frontend = (settings.api_frontend_url or "").rstrip("/")
    # Cross-site (e.g. Vercel → Render) needs SameSite=None + Secure.
    # Local http://localhost can use Lax without Secure.
    cross_site = frontend.startswith("https://") and "localhost" not in frontend
    flags = {
        "key": COOKIE_NAME,
        "httponly": True,
        "secure": cross_site or frontend.startswith("https://"),
        "samesite": "none" if cross_site else "lax",
        "path": "/",
    }
    if remember_me:
        # Persist until JWT_REMEMBER_HOURS (default 30 days)
        flags["max_age"] = int(settings.jwt_remember_hours) * 3600
    # No max_age → browser session cookie (cleared when browser quits)
    return flags


def set_auth_cookie(response: Response, token: str, *, remember_me: bool = False) -> None:
    flags = _cookie_flags(remember_me=remember_me)
    response.set_cookie(value=token, **flags)


def clear_auth_cookie(response: Response) -> None:
    # Delete with both session and persistent variants so logout always works
    for remember in (False, True):
        flags = _cookie_flags(remember_me=remember)
        response.delete_cookie(
            key=flags["key"],
            path=flags["path"],
            secure=flags["secure"],
            httponly=flags["httponly"],
            samesite=flags["samesite"],
        )
