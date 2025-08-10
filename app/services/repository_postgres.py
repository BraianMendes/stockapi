from typing import Optional
from datetime import datetime, UTC
from .aggregator import StockRepository
from ..db.models import StockPurchase, StockSnapshot
from ..models import Stock


class PostgresStockRepository(StockRepository):
    """
    Postgres-backed repository for purchased amounts and stock snapshots.
    """

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def get_purchased_amount(self, symbol: str) -> float:
        with self.session_factory() as db:
            row: Optional[StockPurchase] = db.get(StockPurchase, symbol)
            return float(row.amount) if row else 0.0

    def set_purchased_amount(self, symbol: str, amount: float) -> None:
        with self.session_factory() as db:
            row: Optional[StockPurchase] = db.get(StockPurchase, symbol)
            now = datetime.now(UTC)
            if row:
                row.amount = float(amount)
                row.updated_at = now
            else:
                row = StockPurchase(symbol=symbol, amount=float(amount), updated_at=now)
                db.add(row)
            db.commit()

    def save_snapshot(self, stock: Stock) -> None:
        """
        Upsert a StockSnapshot by (symbol, request_date) with the full payload (by_alias JSON).
        """
        with self.session_factory() as db:
            now = datetime.now(UTC)
            payload = stock.model_dump(mode="json", by_alias=True)
            row: Optional[StockSnapshot] = db.get(StockSnapshot, (stock.company_code, stock.request_data))
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
            db.commit()
