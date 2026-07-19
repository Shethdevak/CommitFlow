"""Vercel / ASGI entrypoint — re-exports the FastAPI app.

Vercel treats files under ``api/`` as individual serverless functions, which
conflicts with our ``api`` Python package. Keep the real app in ``api.main``
and expose it from the repo root for native FastAPI on Vercel.
"""

from api.main import app

__all__ = ["app"]
