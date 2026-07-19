from contextlib import contextmanager
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, Session
from backend.config import get_api_settings
from backend.db.models import Base

_engine = None
_SessionLocal = None


def _normalize_database_url(url: str) -> str:
    """Render often gives postgres://; SQLAlchemy + psycopg3 need postgresql+psycopg://."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _ensure_email_verified_column(engine) -> None:
    """Add users.email_verified for existing DBs; existing rows default to verified."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "email_verified" in cols:
        return
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
        else:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 1"
                )
            )


def init_api_db() -> None:
    global _engine, _SessionLocal
    settings = get_api_settings()
    url = _normalize_database_url(settings.api_database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    Base.metadata.create_all(bind=_engine)
    _ensure_email_verified_column(_engine)


def get_db():
    if _SessionLocal is None:
        init_api_db()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session_ctx():
    if _SessionLocal is None:
        init_api_db()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
