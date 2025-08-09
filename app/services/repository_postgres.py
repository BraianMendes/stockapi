from typing import Optional
from datetime import datetime, UTC
from .aggregator import StockRepository
from ..db.models import StockPurchase


class PostgresStockRepository(StockRepository):
    """
    Postgres-backed repository for purchased amounts.
    """

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def get_purchased_amount(self, symbol: str) -> int:
        with self.session_factory() as db:
            row: Optional[StockPurchase] = db.get(StockPurchase, symbol)
            return int(row.amount) if row else 0

    def set_purchased_amount(self, symbol: str, amount: int) -> None:
        with self.session_factory() as db:
            row: Optional[StockPurchase] = db.get(StockPurchase, symbol)
            now = datetime.now(UTC)
            if row:
                row.amount = int(amount)
                row.updated_at = now
            else:
                row = StockPurchase(symbol=symbol, amount=int(amount), updated_at=now)
                db.add(row)
            db.commit()
