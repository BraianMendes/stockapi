from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, PrimaryKeyConstraint, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StockPurchase(Base):
    __tablename__ = "stock_purchases"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class StockSnapshot(Base):
    """Snapshot of Stock payload per (symbol, date)."""

    __tablename__ = "stock_snapshots"

    symbol: Mapped[str] = mapped_column(String(16))
    request_date: Mapped[date] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        PrimaryKeyConstraint("symbol", "request_date", name="pk_stock_snapshots"),
    )