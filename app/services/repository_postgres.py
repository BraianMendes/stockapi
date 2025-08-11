from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Protocol

from ..db import StockPurchase
from ..models import Stock
from .aggregator import StockRepository


class SessionLike(Protocol):
    def get(self, entity, ident): ...
    def add(self, instance) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class SessionFactory(Protocol):
    def __call__(self) -> AbstractContextManager[SessionLike]: ...


class PostgresStockRepository(StockRepository):
    """Postgres repository for stock purchases."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def get_purchased_amount(self, symbol: str) -> int:
        with self.session_factory() as db:
            row: StockPurchase | None = db.get(StockPurchase, symbol)
            return int(row.amount or 0) if row else 0

    def set_purchased_amount(self, symbol: str, amount: int) -> None:
        with self.session_factory() as db:
            row: StockPurchase | None = db.get(StockPurchase, symbol)
            now = datetime.now(UTC)
            if row:
                row.amount = int(amount)
                row.updated_at = now
            else:
                row = StockPurchase(symbol=symbol, amount=int(amount), updated_at=now)
                db.add(row)
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
