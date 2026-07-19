"""FastAPI entrypoint for CommitFlow web backend.

This package is additive — the existing CLI (`python -m app.cli`) is unchanged.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.config import get_api_settings
from api.db.session import init_api_db
from api.routers import auth as auth_router
from api.routers import settings as settings_router
from api.routers import sync as sync_router
from api.routers import redmine as redmine_router

app = FastAPI(
    title="CommitFlow API",
    description="Multi-user web API for CommitFlow. CLI continues to work independently.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    cfg = get_api_settings()
    # On Vercel, prefer /tmp (only writable path). Local/Docker keep project data/.
    data_root = os.environ.get("API_USER_DATA_DIR", "data/users")
    if data_root.startswith("/tmp") or os.environ.get("VERCEL"):
        os.makedirs("/tmp/commitflow-data", exist_ok=True)
        os.makedirs(data_root, exist_ok=True)
    else:
        os.makedirs("data", exist_ok=True)
        os.makedirs(cfg.api_user_data_dir, exist_ok=True)
    init_api_db()


cfg = get_api_settings()
origins = [o.strip() for o in cfg.api_cors_origins.split(",") if o.strip()]
# Credentials (HttpOnly cookies) require explicit origins — never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(sync_router.router, prefix="/api")
app.include_router(redmine_router.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "commitflow-api"}
