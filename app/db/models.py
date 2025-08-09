from datetime import datetime, UTC
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime, Index


class Base(DeclarativeBase):
    pass


class StockPurchase(Base):
    __tablename__ = "stock_purchases"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_stock_purchases_symbol", "symbol"),
    )