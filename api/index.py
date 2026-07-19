"""Vercel serverless entry — only file under /api (special Vercel functions dir)."""

from __future__ import annotations

import os

from mangum import Mangum

os.makedirs("/tmp/commitflow-data/users", exist_ok=True)
os.environ.setdefault("API_USER_DATA_DIR", "/tmp/commitflow-data/users")

from backend.db.session import init_api_db  # noqa: E402
from backend.main import app  # noqa: E402  — also discovered as ASGI `app`

init_api_db()

# Lambda-style handler for Vercel Python
handler = Mangum(app, lifespan="off")
