from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base
from app.services.repository_postgres import PostgresStockRepository


def make_sqlite_repo():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return PostgresStockRepository(session_factory=SessionLocal)


def test_set_and_get():
    repo = make_sqlite_repo()
    sym = "AAPL"
    assert repo.get_purchased_amount(sym) == 0
    repo.set_purchased_amount(sym, 5)
    assert repo.get_purchased_amount(sym) == 5
    repo.set_purchased_amount(sym, 7)
    assert repo.get_purchased_amount(sym) == 7
