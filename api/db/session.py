from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from api.config import get_api_settings
from api.db.models import Base

_engine = None
_SessionLocal = None


def init_api_db() -> None:
    global _engine, _SessionLocal
    settings = get_api_settings()
    connect_args = {"check_same_thread": False} if settings.api_database_url.startswith("sqlite") else {}
    _engine = create_engine(settings.api_database_url, connect_args=connect_args)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    Base.metadata.create_all(bind=_engine)


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
