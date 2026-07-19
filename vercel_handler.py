"""Vercel serverless entrypoint for the CommitFlow FastAPI app."""

from __future__ import annotations

import os

from mangum import Mangum

# Ensure writable dirs exist in the Lambda-like environment
os.makedirs("/tmp/commitflow-data", exist_ok=True)
os.environ.setdefault("API_USER_DATA_DIR", "/tmp/commitflow-data/users")

from api.db.session import init_api_db  # noqa: E402
from api.main import app  # noqa: E402

# lifespan="off": Vercel invocations are short-lived; init DB on cold start instead
init_api_db()

handler = Mangum(app, lifespan="off")
