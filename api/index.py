"""Vercel serverless entry (api/index.py → hosts all routes via vercel.json routes)."""

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

try:
    from backend.main import app
    from backend.db.session import init_api_db

    try:
        init_api_db()
    except Exception:
        # Don't prevent cold start — /api/health can still respond; DB routes will error clearly
        traceback.print_exc()

    try:
        from mangum import Mangum

        handler = Mangum(app, lifespan="off")
    except Exception:
        traceback.print_exc()
        handler = None
except Exception:
    traceback.print_exc()
    from fastapi import FastAPI

    app = FastAPI(title="CommitFlow API boot-error")

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def _boot_error(full_path: str = ""):
        return {
            "status": "error",
            "detail": "API failed to start. Check Vercel function logs.",
            "path": full_path,
        }

    try:
        from mangum import Mangum

        handler = Mangum(app, lifespan="off")
    except Exception:
        handler = None
