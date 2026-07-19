"""Local / Railway ASGI entry — re-exports FastAPI app."""

from backend.main import app

__all__ = ["app"]
