from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ..utils import EnvConfig
from .models import Base

_cfg = EnvConfig()
_DB_URL_opt = _cfg.get_str("DATABASE_URL", "postgresql+psycopg2://stocks:stocks@localhost:5432/stocks")
_DB_URL = _DB_URL_opt or "postgresql+psycopg2://stocks:stocks@localhost:5432/stocks"

if _DB_URL.startswith("sqlite"):
    is_memory = ":memory:" in _DB_URL
    engine = create_engine(
        _DB_URL,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
        **({"poolclass": StaticPool} if is_memory else {}),
    )
else:
    engine = create_engine(_DB_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Creates tables if absent (dev use)."""
    Base.metadata.create_all(bind=engine)
