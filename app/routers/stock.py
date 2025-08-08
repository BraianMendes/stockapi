# app/routers/stock.py
from typing import Dict, Optional
from datetime import date
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..models import Stock
from ..services.aggregator import StockAggregator
from ..services.repository_postgres import PostgresStockRepository
from ..db.database import SessionLocal
from ..utils import EnvConfig, RedisCache

router = APIRouter(prefix="/stock", tags=["Stock"])

_repo = PostgresStockRepository(session_factory=SessionLocal)
_aggregator = StockAggregator(repo=_repo)


class PurchaseBody(BaseModel):
    amount: int = Field(..., ge=0, description="Purchased amount (integer)")


@router.get("/{symbol}", response_model=Stock, summary="Get stock payload")
def get_stock(symbol: str, request_date: Optional[date] = Query(None, description="YYYY-MM-DD")) -> Stock:
    """
    Return full Stock payload (Polygon OHLC + MarketWatch performance/competitors).
    Cached per (symbol, request_date).
    """
    try:
        return _aggregator.get_stock(symbol, request_date)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.post("/{symbol}", status_code=status.HTTP_201_CREATED, summary="Add purchased amount")
def add_purchase(symbol: str, body: PurchaseBody) -> Dict[str, str]:
    """
    Persist purchased amount for a symbol and invalidate aggregator cache for this symbol.
    """
    try:
        sym = symbol.strip().upper()
        _repo.set_purchased_amount(sym, body.amount)
        _invalidate_symbol_cache(sym)
        return {"message": f"{body.amount} units of stock {sym} were added to your stock record"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _invalidate_symbol_cache(symbol: str) -> None:
    """
    Remove all cached entries for this symbol (all dates) when using Redis.
    In-memory cache has no pattern delete; that's fine for local dev.
    """
    cfg = EnvConfig()
    redis_url = cfg.get_str("REDIS_URL")
    if redis_url and RedisCache is not None:
        rc = RedisCache(url=redis_url, prefix="stocks")
        for k in rc.client.scan_iter(f"{rc.prefix}:stock:{symbol}:*"):
            rc.client.delete(k)
