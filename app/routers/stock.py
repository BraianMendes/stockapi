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
from ..utils.error_codes import ErrorCode

router = APIRouter(prefix="/stock", tags=["Stock"])

_repo = PostgresStockRepository(session_factory=SessionLocal)
_aggregator = StockAggregator(repo=_repo)


class PurchaseBody(BaseModel):
    amount: float = Field(..., ge=0, description="Purchased amount (float)")


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9\.-]{0,15}$")

TODAY_STR = date.today().isoformat()


def _symbol_or_400(symbol: str) -> str:
    sym = str(symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": ErrorCode.INVALID_SYMBOL, "message": "Invalid stock symbol"})
    return sym


def _http_error(detail_code: ErrorCode | str, message: str, *, http_status: int = status.HTTP_502_BAD_GATEWAY):
    code = str(detail_code)
    raise HTTPException(status_code=http_status, detail={"code": code, "message": message})


def _set_meta_headers(response: Response) -> None:
    meta = getattr(_aggregator, "last_meta", {}) or {}
    response.headers["X-Cache"] = str(meta.get("cache") or "")
    response.headers["X-MarketWatch-Status"] = str(meta.get("marketwatch_status") or "")
    response.headers["X-MarketWatch-Used-Cookie"] = "true" if meta.get("mw_used_cookie") else "false"


@router.get("/{symbol}", response_model=Stock, summary="Get stock payload")
def get_stock(
    response: Response,
    symbol: str = Path(
        ...,
        description="Ticker symbol (path)",
        example="AAPL",
    ),
    request_date: Optional[date] = Query(
        None,
        description="YYYY-MM-DD",
        example=TODAY_STR,
    ),
) -> Stock:
    sym = _symbol_or_400(symbol)
    try:
        stock = _aggregator.get_stock(sym, request_date)
        _set_meta_headers(response)
        try:
            _repo.save_snapshot(stock)
        except Exception:
            pass
        return stock
    except PolygonError as e:
        msg = str(e).lower()
        if "unauthorized" in msg:
            _http_error(ErrorCode.POLYGON_UNAUTHORIZED, "Polygon API unauthorized")
        elif "rate_limited" in msg or "rate" in msg:
            _http_error(ErrorCode.POLYGON_RATE_LIMITED, "Polygon API rate limited")
        else:
            _http_error(ErrorCode.POLYGON_HTTP_ERROR, "Polygon API error")
    except HTTPException:
        raise
    except Exception:
        _http_error(ErrorCode.UPSTREAM_ERROR, "Failed to retrieve stock data")


@router.post("/{symbol}", status_code=status.HTTP_201_CREATED, summary="Add purchased amount")
def add_purchase(
    response: Response,
    symbol: str = Path(
        ...,
        description="Ticker symbol (path)",
        example="AAPL",
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
        example=TODAY_STR,
    ),
):
    sym = _symbol_or_400(symbol)
    try:
        stock = _aggregator.get_stock(sym, request_date)
        _set_meta_headers(response)

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
            _http_error(ErrorCode.POLYGON_UNAUTHORIZED, "Polygon API unauthorized")
        elif "rate_limited" in msg or "rate" in msg:
            _http_error(ErrorCode.POLYGON_RATE_LIMITED, "Polygon API rate limited")
        else:
            _http_error(ErrorCode.POLYGON_HTTP_ERROR, "Polygon API error")
    except HTTPException:
        raise
    except Exception:
        _http_error(ErrorCode.PURCHASE_ERROR, "Failed to add purchased amount", http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _invalidate_symbol_cache(symbol: str) -> None:
    cfg = EnvConfig()
    redis_url = cfg.get_str("REDIS_URL")
    if redis_url and RedisCache is not None:
        try:
            rc = RedisCache(url=redis_url, prefix="stocks")
            rc.delete_by_symbol(symbol)
        except Exception:
            pass
    else:
        cache = getattr(_aggregator, "cache", None)
        if cache is not None and hasattr(cache, "delete_by_symbol"):
            try:
                cache.delete_by_symbol(symbol)
            except Exception:
                pass
