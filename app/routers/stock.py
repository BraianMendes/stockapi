import re
from datetime import date
from typing import NoReturn

from fastapi import APIRouter, Body, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field

from ..db import SessionLocal
from ..models import Stock
from ..services.aggregator import StockAggregator
from ..services.repository_postgres import PostgresStockRepository
from ..utils import (
    EnvConfig,
    ErrorCode,
    PolygonError,
    RedisCache,
    is_business_day,
    last_business_day,
    roll_to_business_day,
)

router = APIRouter(prefix="/stock", tags=["Stock"]) 

_repo = PostgresStockRepository(session_factory=SessionLocal)
_aggregator = StockAggregator(repo=_repo)


class PurchaseBody(BaseModel):
    amount: int = Field(
        ...,
        ge=0,
        description="Purchased amount (integer)",
        json_schema_extra={"example": 100},
    )


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9\.-]{0,15}$")

DEFAULT_DATE = last_business_day()
SWAGGER_DATE_EXAMPLE = "2025-08-05"


def _symbol_or_400(symbol: str) -> str:
    sym = str(symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": ErrorCode.INVALID_SYMBOL, "message": "Invalid stock symbol"})
        
    return sym


def _http_error(detail_code: ErrorCode | str, message: str, *, http_status: int = status.HTTP_502_BAD_GATEWAY) -> NoReturn:
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
        examples=[{"summary": "Example symbol", "value": "AAPL"}],
        openapi_extra={"example": "AAPL"},
        json_schema_extra={"example": "AAPL"},
    ),
    request_date: date | None = Query(
        DEFAULT_DATE,
        description="YYYY-MM-DD",
        examples=[{"summary": "Example date", "value": SWAGGER_DATE_EXAMPLE}],
        openapi_extra={"example": SWAGGER_DATE_EXAMPLE},
        json_schema_extra={"example": SWAGGER_DATE_EXAMPLE},
    ),
    strict: bool = Query(
        False,
        description="If true, do not adjust non-business dates; return 422",
    ),
) -> Stock:
    sym = _symbol_or_400(symbol)

    effective_date: date | None = request_date
    reason = "none"

    if request_date is not None and not is_business_day(request_date):
        if strict:
            _http_error(ErrorCode.INVALID_NON_BUSINESS_DATE, "Requested date is not a business day", http_status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        effective_date, reason = roll_to_business_day(request_date, policy="previous")

    try:
        stock = _aggregator.get_stock(sym, effective_date)
        _set_meta_headers(response)
        response.headers["X-Request-Date"] = request_date.isoformat() if request_date else ""
        response.headers["X-Effective-Date"] = effective_date.isoformat() if effective_date else str(stock.request_data)
        response.headers["X-Date-Policy"] = "previous"
        response.headers["X-Date-Adjustment-Reason"] = reason
        
        return stock
    except PolygonError as e:
        msg = str(e).lower()
        if "unauthorized" in msg:
            _http_error(ErrorCode.POLYGON_UNAUTHORIZED, "Polygon API unauthorized")
        elif "rate_limited" in msg or "rate" in msg:
            _http_error(ErrorCode.POLYGON_RATE_LIMITED, "Polygon API rate limited")
        elif "not_found" in msg:
            _http_error(ErrorCode.MARKET_CLOSED, "No market data for the requested date", http_status=status.HTTP_404_NOT_FOUND)
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
        examples=[{"summary": "Example symbol", "value": "AAPL"}],
        openapi_extra={"example": "AAPL"},
        json_schema_extra={"example": "AAPL"},
    ),
    body: PurchaseBody = Body(
        ...,
        examples={"amount": 5},
    ),
    request_date: date | None = Query(
        DEFAULT_DATE,
        description="YYYY-MM-DD",
        examples=[{"summary": "Example date", "value": SWAGGER_DATE_EXAMPLE}],
        openapi_extra={"example": SWAGGER_DATE_EXAMPLE},
        json_schema_extra={"example": SWAGGER_DATE_EXAMPLE},
    ),
    strict: bool = Query(
        False,
        description="If true, do not adjust non-business dates; return 422",
    ),
) -> dict:
    sym = _symbol_or_400(symbol)

    effective_date: date | None = request_date
    reason = "none"
    if request_date is not None and not is_business_day(request_date):
        if strict:
            _http_error(ErrorCode.INVALID_NON_BUSINESS_DATE, "Requested date is not a business day", http_status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        effective_date, reason = roll_to_business_day(request_date, policy="previous")

    try:
        amount = body.amount
        if not isinstance(amount, int):
            _http_error(ErrorCode.PURCHASE_ERROR, "Amount must be an integer", http_status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        if amount < 0:
            _http_error(ErrorCode.PURCHASE_ERROR, "Amount must be non-negative", http_status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except Exception:
        _http_error(ErrorCode.PURCHASE_ERROR, "Field 'amount' is required and must be an integer", http_status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    try:
        stock = _aggregator.get_stock(sym, effective_date)
        _set_meta_headers(response)
        response.headers["X-Request-Date"] = request_date.isoformat() if request_date else ""
        response.headers["X-Effective-Date"] = effective_date.isoformat() if effective_date else str(stock.request_data)
        response.headers["X-Date-Policy"] = "previous"
        response.headers["X-Date-Adjustment-Reason"] = reason

        _repo.set_purchased_amount(sym, amount)
        stock.purchased_amount = int(amount)
        stock.purchased_status = "purchased" if stock.purchased_amount > 0 else "not_purchased"
        _invalidate_symbol_cache(sym)
        return {"message": f"{amount} units of stock {sym} were added to your stock record"}
    except PolygonError as e:
        msg = str(e).lower()
        if "unauthorized" in msg:
            _http_error(ErrorCode.POLYGON_UNAUTHORIZED, "Polygon API unauthorized")
        elif "rate_limited" in msg or "rate" in msg:
            _http_error(ErrorCode.POLYGON_RATE_LIMITED, "Polygon API rate limited")
        elif "not_found" in msg:
            _http_error(ErrorCode.MARKET_CLOSED, "No market data for the requested date", http_status=status.HTTP_404_NOT_FOUND)
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
