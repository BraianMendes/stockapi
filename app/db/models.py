from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StockPurchase(Base):
    __tablename__ = "stock_purchases"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))