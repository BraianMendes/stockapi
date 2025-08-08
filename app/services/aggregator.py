from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Union, List
from datetime import date, datetime, timedelta

from ..models import Stock, StockValues, PerformanceData, Competitor, MarketCap
from ..utils import EnvConfig, IsoDate, Symbol, RedisCache
try:
    from ..utils import RedisCache
except Exception:
    RedisCache = None
from .polygon_service import PolygonService
from .marketwatch_service import MarketWatchService


class StockRepository(Protocol):
    def get_purchased_amount(self, symbol: str) -> int: ...
    def set_purchased_amount(self, symbol: str, amount: int) -> None: ...


class Cache(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    def clear(self) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class RealClock:
    def now(self) -> datetime:
        return datetime.utcnow()


@dataclass
class InMemoryCache:
    _store: Dict[str, Any] = None
    _expires: Dict[str, datetime] = None
    _clock: Clock = RealClock()

    def __post_init__(self) -> None:
        if self._store is None:
            self._store = {}
        if self._expires is None:
            self._expires = {}

    def get(self, key: str) -> Optional[Any]:
        exp = self._expires.get(key)
        if exp and exp > self._clock.now():
            return self._store.get(key)
        if key in self._store:
            del self._store[key]
            self._expires.pop(key, None)
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = value
        self._expires[key] = self._clock.now() + timedelta(seconds=ttl_seconds)

    def clear(self) -> None:
        self._store.clear()
        self._expires.clear()


class StockAggregator:
    """
    Orchestrates external sources (Polygon, MarketWatch) and builds a Stock payload.
    Uses Redis cache when REDIS_URL is set; otherwise falls back to in-memory cache.
    """

    def __init__(
        self,
        polygon: Optional[PolygonService] = None,
        marketwatch: Optional[MarketWatchService] = None,
        repo: Optional[StockRepository] = None,
        cache: Optional[Cache] = None,
        config: Optional[EnvConfig] = None,
        clock: Optional[Clock] = None,
    ) -> None:
        self.polygon = polygon or PolygonService()
        self.marketwatch = marketwatch or MarketWatchService()
        self.repo = repo
        self.cfg = config or EnvConfig()
        self.clock = clock or RealClock()
        self.cache_ttl = int(self.cfg.get_int("CACHE_TTL_SECONDS", 300))

        # Prefer explicit cache param; else try Redis; else in-memory
        if cache is not None:
            self.cache = cache
        else:
            redis_url = self.cfg.get_str("REDIS_URL")
            if redis_url and RedisCache is not None:
                self.cache = RedisCache(url=redis_url, prefix="stocks")
            else:
                self.cache = InMemoryCache()

    def get_stock(self, symbol: str, request_date: Union[str, date, None]) -> Stock:
        sym = Symbol.of(symbol).value
        req_date_str = self._resolve_request_date_str(request_date)
        cache_key = f"stock:{sym}:{req_date_str}"

        cached = self.cache.get(cache_key)
        if cached is not None:
            return Stock.model_validate(cached)

        ohlc = self.polygon.get_ohlc(sym, req_date_str)
        mw = self.marketwatch.get_overview(sym)

        purchased_amount = self._safe_get_amount(sym)
        purchased_status = "purchased" if purchased_amount > 0 else "not_purchased"

        performance_raw: Dict[str, Any] = mw.get("performance") or {}
        competitors_raw: List[Dict[str, Any]] = mw.get("competitors") or []
        company_name = mw.get("company_name") or sym

        stock = Stock(
            status=ohlc.get("status", "ok"),
            purchased_amount=int(purchased_amount),
            purchased_status=purchased_status,
            request_data=self._to_date(req_date_str),
            company_code=sym,
            company_name=company_name,
            stock_values=StockValues(
                open=float(ohlc["open"]),
                high=float(ohlc["high"]),
                low=float(ohlc["low"]),
                close=float(ohlc["close"]),
            ),
            performance_data=PerformanceData(
                five_days=self._to_opt_float(performance_raw.get("five_days")),
                one_month=self._to_opt_float(performance_raw.get("one_month")),
                three_months=self._to_opt_float(performance_raw.get("three_months")),
                year_to_date=self._to_opt_float(performance_raw.get("year_to_date")),
                one_year=self._to_opt_float(performance_raw.get("one_year")),
            ),
            competitors=self._map_competitors(competitors_raw),
        )

        self.cache.set(cache_key, stock.model_dump(), self.cache_ttl)
        return stock

    def _map_competitors(self, items: List[Dict[str, Any]]) -> List[Competitor]:
        result: List[Competitor] = []
        for c in items:
            name = c.get("name")
            mc = c.get("market_cap")
            market_cap = None
            if isinstance(mc, dict) and mc.get("currency") and mc.get("value") is not None:
                market_cap = MarketCap(currency=str(mc["currency"]), value=float(mc["value"]))
            if name:
                result.append(Competitor(name=str(name), market_cap=market_cap))
        return result

    def _resolve_request_date_str(self, d: Union[str, date, None]) -> str:
        if d is None:
            return IsoDate.from_any(date.today()).value
        return IsoDate.from_any(d).value

    def _to_date(self, s: str) -> date:
        return date.fromisoformat(s)

    def _to_opt_float(self, v: Any) -> Optional[float]:
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    def _safe_get_amount(self, symbol: str) -> int:
        if self.repo is None:
            return 0
        try:
            return int(self.repo.get_purchased_amount(symbol))
        except Exception:
            return 0
