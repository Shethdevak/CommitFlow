"""ASGI entry for Vercel FastAPI runtime (`[tool.vercel] entrypoint = "main:app"`)."""

from api.main import app

__all__ = ["app"]
