from typing import Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from ..utils import EnvConfig
from .models import Base


_cfg = EnvConfig()
_DB_URL = _cfg.get_str("DATABASE_URL", "postgresql+psycopg2://stocks:stocks@localhost:5432/stocks")

engine = create_engine(_DB_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """
    Create tables if not exist (dev-friendly). For prod, prefer Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """
    FastAPI dependency to yield a session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
