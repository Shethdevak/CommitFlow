"""FastAPI entrypoint for CommitFlow web backend.

This package is additive — the existing CLI (`python -m app.cli`) is unchanged.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import get_api_settings
from backend.db.session import init_api_db
from backend.routers import auth as auth_router
from backend.routers import settings as settings_router
from backend.routers import sync as sync_router
from backend.routers import redmine as redmine_router

app = FastAPI(
    title="CommitFlow API",
    description="Multi-user web API for CommitFlow. CLI continues to work independently.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    cfg = get_api_settings()
    # Vercel only allows writes under /tmp
    if os.environ.get("VERCEL"):
        os.environ.setdefault("API_USER_DATA_DIR", "/tmp/commitflow-data/users")
        os.makedirs("/tmp/commitflow-data/users", exist_ok=True)
    else:
        os.makedirs("data", exist_ok=True)
        os.makedirs(cfg.api_user_data_dir, exist_ok=True)
    try:
        init_api_db()
    except Exception:
        # Allow process to start; failing routes return DB errors instead of a silent boot crash
        import traceback

        traceback.print_exc()


def _cors_origins() -> list[str]:
    """Merge env list + frontend URL + known local/prod fronts (credentials require exact origins)."""
    cfg = get_api_settings()
    origins: list[str] = []
    for part in (cfg.api_cors_origins or "").split(","):
        o = part.strip().rstrip("/")
        if o and o not in origins:
            origins.append(o)
    frontend = (cfg.api_frontend_url or "").strip().rstrip("/")
    if frontend and frontend not in origins:
        origins.append(frontend)
    for extra in (
        "https://commit-flow-two.vercel.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ):
        if extra not in origins:
            origins.append(extra)
    return origins


# Credentials (HttpOnly cookies) require explicit origins — never "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
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
