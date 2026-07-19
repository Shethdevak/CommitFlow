"""Vercel serverless entry — must expose top-level ``app`` and/or ``handler``."""

from __future__ import annotations

import os
import sys
import traceback

# Repo root on sys.path (Vercel function cwd can vary)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.makedirs("/tmp/commitflow-data/users", exist_ok=True)
os.environ.setdefault("API_USER_DATA_DIR", "/tmp/commitflow-data/users")

from backend.main import app  # noqa: E402  — required top-level ASGI `app`
from backend.db.session import init_api_db  # noqa: E402

try:
    init_api_db()
except Exception:
    traceback.print_exc()

from mangum import Mangum  # noqa: E402

# Required top-level Lambda-style `handler` for older Vercel Python adapters
handler = Mangum(app, lifespan="off")
