from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Protocol

from ..db import StockPurchase, StockSnapshot
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
    """Postgres repository for purchases and snapshots."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def get_purchased_amount(self, symbol: str) -> float:
        with self.session_factory() as db:
            row: StockPurchase | None = db.get(StockPurchase, symbol)
            return float(row.amount or 0.0) if row else 0.0

    def set_purchased_amount(self, symbol: str, amount: float) -> None:
        with self.session_factory() as db:
            row: StockPurchase | None = db.get(StockPurchase, symbol)
            now = datetime.now(UTC)
            if row:
                row.amount = float(amount)
                row.updated_at = now
            else:
                row = StockPurchase(symbol=symbol, amount=float(amount), updated_at=now)
                db.add(row)
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise

    def save_snapshot(self, stock: Stock) -> None:
        """Upserts a StockSnapshot for (symbol, date)."""
        with self.session_factory() as db:
            now = datetime.now(UTC)
            payload = stock.model_dump(mode="json", by_alias=True)
            row: StockSnapshot | None = db.get(StockSnapshot, (stock.company_code, stock.request_data))
            if row:
                row.payload = payload
                row.updated_at = now
            else:
                row = StockSnapshot(
                    symbol=stock.company_code,
                    request_date=stock.request_data,
                    payload=payload,
                    updated_at=now,
                )
                db.add(row)
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
