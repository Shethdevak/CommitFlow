"""HttpOnly session cookie helpers for JWT auth."""

from fastapi import Response
from api.config import get_api_settings

COOKIE_NAME = "cf_session"


def _cookie_flags() -> dict:
    settings = get_api_settings()
    frontend = (settings.api_frontend_url or "").rstrip("/")
    # Cross-site (e.g. Vercel → Render) needs SameSite=None + Secure.
    # Local http://localhost can use Lax without Secure.
    cross_site = frontend.startswith("https://") and "localhost" not in frontend
    return {
        "key": COOKIE_NAME,
        "httponly": True,
        "secure": cross_site or frontend.startswith("https://"),
        "samesite": "none" if cross_site else "lax",
        "max_age": int(settings.jwt_expire_hours) * 3600,
        "path": "/",
    }


def set_auth_cookie(response: Response, token: str) -> None:
    flags = _cookie_flags()
    response.set_cookie(value=token, **flags)


def clear_auth_cookie(response: Response) -> None:
    flags = _cookie_flags()
    response.delete_cookie(
        key=flags["key"],
        path=flags["path"],
        secure=flags["secure"],
        httponly=flags["httponly"],
        samesite=flags["samesite"],
    )
