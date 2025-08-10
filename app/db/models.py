from datetime import datetime, UTC, date
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, Index, JSON, Float


class Base(DeclarativeBase):
    pass


class StockPurchase(Base):
    __tablename__ = "stock_purchases"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class StockSnapshot(Base):
    """
    Stores full Stock payload snapshots per (symbol, request_date).
    Uses JSON column (SQLite stores as TEXT under the hood).
    """

    __tablename__ = "stock_snapshots"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    request_date: Mapped[date] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_stock_snapshots_symbol_date", "symbol", "request_date"),
    )