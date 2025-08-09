from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Union, List
from datetime import date, datetime, timedelta, UTC

from ..models import Stock, StockValues, PerformanceData, Competitor, MarketCap
from ..utils import EnvConfig, IsoDate, Symbol, RedisCache, ScraperError
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
        return datetime.now(UTC)


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

        try:
            mw = self.marketwatch.get_overview(sym)
        except ScraperError:
            mw = {"company_name": sym, "performance": {}, "competitors": []}

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
                five_days=self._to_float_zero(performance_raw.get("five_days")),
                one_month=self._to_float_zero(performance_raw.get("one_month")),
                three_months=self._to_float_zero(performance_raw.get("three_months")),
                year_to_date=self._to_float_zero(performance_raw.get("year_to_date")),
                one_year=self._to_float_zero(performance_raw.get("one_year")),
            ),
            competitors=self._map_competitors(competitors_raw),
        )

        # Ensure JSON-friendly dict (dates -> strings) and use aliases for consistency
        self.cache.set(cache_key, stock.model_dump(mode="json", by_alias=True), self.cache_ttl)
        return stock

    def _map_competitors(self, items: List[Dict[str, Any]]) -> List[Competitor]:
        result: List[Competitor] = []
        for c in items:
            name = c.get("name") or c.get("symbol")
            mc = c.get("market_cap") or {}
            cur = mc.get("currency") or "USD"
            val = mc.get("value")
            try:
                val_f = float(val) if val is not None else 0.0
            except Exception:
                val_f = 0.0
            if name:
                result.append(Competitor(name=str(name).strip(), market_cap=MarketCap(currency=str(cur), value=val_f)))
        return result

    def _resolve_request_date_str(self, d: Union[str, date, None]) -> str:
        # Se não for informado, usar o último dia útil (evita fins de semana/feriados em dev)
        if d is None:
            return IsoDate.from_any(self._last_business_day()).value
        return IsoDate.from_any(d).value

    def _last_business_day(self, start: Optional[date] = None) -> date:
        d = (start or date.today()) - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    def _to_date(self, s: str) -> date:
        return date.fromisoformat(s)

    def _to_float_zero(self, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    def _safe_get_amount(self, symbol: str) -> int:
        if self.repo is None:
            return 0
        try:
            return int(self.repo.get_purchased_amount(symbol))
        except Exception:
            return 0
