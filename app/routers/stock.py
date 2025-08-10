from typing import Optional
from datetime import date
from fastapi import APIRouter, HTTPException, Query, status, Path, Body, Response
from pydantic import BaseModel, Field
import re

from ..models import Stock
from ..services.aggregator import StockAggregator, InMemoryCache
from ..services.repository_postgres import PostgresStockRepository
from ..db.database import SessionLocal
from ..utils import EnvConfig, RedisCache
from ..utils.errors import PolygonError

router = APIRouter(prefix="/stock", tags=["Stock"])

_repo = PostgresStockRepository(session_factory=SessionLocal)
_aggregator = StockAggregator(repo=_repo)


class PurchaseBody(BaseModel):
    amount: float = Field(..., ge=0, description="Purchased amount (float)")


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9\.-]{0,15}$")

def _symbol_or_400(symbol: str) -> str:
    sym = str(symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_symbol", "message": "Invalid stock symbol"})
    return sym


def _http_error(detail_code: str, message: str, *, http_status: int = status.HTTP_502_BAD_GATEWAY):
    raise HTTPException(status_code=http_status, detail={"code": detail_code, "message": message})


@router.get("/{symbol}", response_model=Stock, summary="Get stock payload")
def get_stock(
    response: Response,
    symbol: str = Path(
        ...,
        description="Ticker symbol (path)",
        examples={
            "AAPL": {"summary": "Apple", "value": "AAPL"},
            "DELL": {"summary": "Dell Technologies", "value": "DELL"},
            "HPQ": {"summary": "HP Inc.", "value": "HPQ"},
        },
    ),
    request_date: Optional[date] = Query(
        None,
        description="YYYY-MM-DD",
        examples={"default": {"summary": "Request date", "value": "2025-05-05"}},
    ),
    refresh: bool = Query(
        False,
        description="When true, bypass cache and re-fetch upstream data (useful after setting cookie)",
    ),
) -> Stock:
    sym = _symbol_or_400(symbol)
    try:
        stock = _aggregator.get_stock(sym, request_date, bypass_cache=bool(refresh))
        meta = getattr(_aggregator, "last_meta", {}) or {}
        response.headers["X-Cache"] = str(meta.get("cache") or "")
        response.headers["X-MarketWatch-Status"] = str(meta.get("marketwatch_status") or "")
        response.headers["X-MarketWatch-Used-Cookie"] = "true" if meta.get("mw_used_cookie") else "false"
        try:
            _repo.save_snapshot(stock)
        except Exception:
            pass
        return stock
    except PolygonError as e:
        msg = str(e).lower()
        if "unauthorized" in msg:
            _http_error("polygon_unauthorized", "Polygon API unauthorized")
        elif "rate_limited" in msg or "rate" in msg:
            _http_error("polygon_rate_limited", "Polygon API rate limited")
        else:
            _http_error("polygon_http_error", "Polygon API error")
    except HTTPException:
        raise
    except Exception:
        _http_error("upstream_error", "Failed to retrieve stock data")


@router.post("/{symbol}", status_code=status.HTTP_201_CREATED, summary="Add purchased amount")
def add_purchase(
    response: Response,
    symbol: str = Path(
        ...,
        description="Ticker symbol (path)",
        examples={
            "AAPL": {"summary": "Apple", "value": "AAPL"},
            "DELL": {"summary": "Dell Technologies", "value": "DELL"},
            "HPQ": {"summary": "HP Inc.", "value": "HPQ"},
        },
    ),
    body: PurchaseBody = Body(
        ...,
        examples={
            "default": {"summary": "Example purchase body", "value": {"amount": 10.0}},
            "dell": {"summary": "Dell sample", "value": {"amount": 5.0}},
            "hp": {"summary": "HP sample", "value": {"amount": 2.5}},
        },
    ),
    request_date: Optional[date] = Query(
        None,
        description="YYYY-MM-DD",
        examples={"default": {"summary": "Request date", "value": "2025-05-05"}},
    ),
    refresh: bool = Query(
        False,
        description="When true, bypass cache and re-fetch upstream data before saving",
    ),
):
    sym = _symbol_or_400(symbol)
    try:
        stock = _aggregator.get_stock(sym, request_date, bypass_cache=bool(refresh))
        meta = getattr(_aggregator, "last_meta", {}) or {}
        response.headers["X-Cache"] = str(meta.get("cache") or "")
        response.headers["X-MarketWatch-Status"] = str(meta.get("marketwatch_status") or "")
        response.headers["X-MarketWatch-Used-Cookie"] = "true" if meta.get("mw_used_cookie") else "false"

        _repo.set_purchased_amount(sym, body.amount)
        stock.purchased_amount = float(body.amount)
        stock.purchased_status = "purchased" if stock.purchased_amount > 0 else "not_purchased"
        try:
            _repo.save_snapshot(stock)
        except Exception:
            pass
        _invalidate_symbol_cache(sym)
        return {"message": f"{body.amount} units of stock {sym} were added to your stock record"}
    except PolygonError as e:
        msg = str(e).lower()
        if "unauthorized" in msg:
            _http_error("polygon_unauthorized", "Polygon API unauthorized")
        elif "rate_limited" in msg or "rate" in msg:
            _http_error("polygon_rate_limited", "Polygon API rate limited")
        else:
            _http_error("polygon_http_error", "Polygon API error")
    except HTTPException:
        raise
    except Exception:
        _http_error("purchase_error", "Failed to add purchased amount", http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _invalidate_symbol_cache(symbol: str) -> None:
    cfg = EnvConfig()
    redis_url = cfg.get_str("REDIS_URL")
    if redis_url and RedisCache is not None:
        from ..utils.redis_cache import RedisCache as _RC
        rc = _RC(url=redis_url, prefix="stocks")
        for k in rc.client.scan_iter(f"{rc.prefix}:stock:{symbol}:*"):
            rc.client.delete(k)
    else:
        cache = getattr(_aggregator, "cache", None)
        if isinstance(cache, InMemoryCache):
            cache.delete_by_symbol(symbol)
