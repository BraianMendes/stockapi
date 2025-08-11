from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.repository_postgres import PostgresStockRepository


def make_sqlite_repo():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    repo = PostgresStockRepository(session_factory=SessionLocal)
    repo._test_engine = engine
    return repo


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
