import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()
_SessionLocal = None
_engine = None

def init_db(db_path: str) -> None:
    """Initializes the SQLAlchemy engine and creates all tables."""
    global _SessionLocal, _engine
    
    # Ensure parent directories exist
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    db_url = f"sqlite:///{db_path}"
    _engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False}
    )
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    Base.metadata.create_all(bind=_engine)

def get_session() -> Session:
    """Returns a direct SQLAlchemy session instance. Should be closed after use."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db(db_path) first.")
    return _SessionLocal()

@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager for SQLAlchemy database sessions, handling rollbacks and closures."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
