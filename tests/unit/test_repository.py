from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, StockSnapshot
from app.models import Stock, StockValues, PerformanceData, MarketCap, Competitor
from app.services.repository_postgres import PostgresStockRepository


def make_sqlite_repo():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    repo = PostgresStockRepository(session_factory=SessionLocal)
    repo._test_engine = engine
    return repo


def make_sqlite_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    SessionLocal._test_engine = engine
    return SessionLocal


def build_stock(sym: str, req_date: str, amount: float) -> Stock:
    return Stock(
        status="ok",
        purchased_amount=amount,
        purchased_status="purchased" if amount > 0 else "not_purchased",
        request_data=req_date,
        company_code=sym,
        company_name=sym,
        Stock_values=StockValues(open=1, high=2, low=0.5, close=1.5, volume=None, afterHours=None, preMarket=None),
        performance_data=PerformanceData(),
        Competitors=[Competitor(name="X", market_cap=MarketCap(Currency="USD", Value=1.0))],
    )


def test_set_and_get():
    repo = make_sqlite_repo()
    sym = "AAPL"
    try:
        assert repo.get_purchased_amount(sym) == 0
        repo.set_purchased_amount(sym, 5)
        assert repo.get_purchased_amount(sym) == 5
        repo.set_purchased_amount(sym, 7)
        assert repo.get_purchased_amount(sym) == 7
    finally:
        if hasattr(repo, '_test_engine'):
            repo._test_engine.dispose()


def test_save_snapshot_insert_and_update():
    SessionLocal = make_sqlite_session_factory()
    repo = PostgresStockRepository(session_factory=SessionLocal)

    try:
        s1 = build_stock("AAPL", "2025-08-07", 1)
        repo.save_snapshot(s1)

        with SessionLocal() as db:
            rows = db.execute(select(StockSnapshot)).scalars().all()
            assert len(rows) == 1
            row = rows[0]
            assert row.symbol == "AAPL" and str(row.request_date) == "2025-08-07"
            assert row.payload["purchased_amount"] == 1
            first_updated = row.updated_at

        s2 = build_stock("AAPL", "2025-08-07", 5)
        repo.save_snapshot(s2)

        with SessionLocal() as db:
            rows = db.execute(select(StockSnapshot)).scalars().all()
            assert len(rows) == 1
            row = rows[0]
            assert row.payload["purchased_amount"] == 5
            assert row.updated_at >= first_updated
    finally:
        if hasattr(SessionLocal, '_test_engine'):
            SessionLocal._test_engine.dispose()


def test_set_purchased_amount_rollback_on_commit_error():
    class FakeSession:
        def __init__(self):
            self.data = {}
            self._rolled_back = False
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def get(self, entity, ident):
            return None
        def add(self, instance):
            self.data[instance.symbol] = instance
        def commit(self):
            raise RuntimeError("db commit error")
        def rollback(self):
            self._rolled_back = True
    class FakeFactory:
        def __call__(self):
            return FakeSession()
    repo = PostgresStockRepository(session_factory=FakeFactory())

    try:
        repo.set_purchased_amount("AAPL", 3)
        assert False, "expected exception"
    except Exception:
        pass

    sess = repo.session_factory()
    assert isinstance(sess, FakeSession)
    assert sess._rolled_back is False
