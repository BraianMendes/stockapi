from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from ..models import Competitor, MarketCap, PerformanceData, Stock, StockValues
from ..utils import EnvConfig, IsoDate, RedisCache, Symbol, last_business_day, to_float_or_zero
from .marketwatch_service import MarketWatchService
from .polygon_service import PolygonService


class StockRepository(Protocol):
    def get_purchased_amount(self, symbol: str) -> int: ...
    def set_purchased_amount(self, symbol: str, amount: int) -> None: ...


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class RealClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass
class InMemoryCache:
    _store: dict[str, Any] = field(default_factory=dict)
    _expires: dict[str, datetime] = field(default_factory=dict)
    _clock: Clock = RealClock()

    def get(self, key: str) -> Any | None:
        now = self._clock.now()
        exp = self._expires.get(key)
        if exp and exp > now:
            return self._store.get(key)
        if key in self._store:
            self._store.pop(key, None)
            self._expires.pop(key, None)
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = value
        self._expires[key] = self._clock.now() + timedelta(seconds=ttl_seconds)

    def delete_by_symbol(self, symbol: str) -> int:
        prefix = f"stock:{symbol.upper()}:"
        to_del = [k for k in list(self._store.keys()) if k.startswith(prefix)]
        for k in to_del:
            self._store.pop(k, None)
            self._expires.pop(k, None)
        return len(to_del)


class StockAggregator:
    """Combines Polygon and MarketWatch into a Stock payload with caching."""

    def __init__(
        self,
        polygon: PolygonService | None = None,
        marketwatch: MarketWatchService | None = None,
        repo: StockRepository | None = None,
        cache: Cache | None = None,
        config: EnvConfig | None = None,
        clock: Clock | None = None,
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

        self.last_meta: dict[str, Any] = {}

    def _cache_get(self, key: str) -> Any | None:
        try:
            return self.cache.get(key)
        except Exception:
            return None

    def _cache_set(self, key: str, value: Any) -> None:
        try:
            self.cache.set(key, value, self.cache_ttl)
        except Exception:
            pass

    def get_stock(self, symbol: str, request_date: str | date | None, *, bypass_cache: bool = False) -> Stock:
        self.last_meta = {}

        sym = Symbol.of(symbol).value
        req_date_str = self._resolve_request_date_str(request_date)
        cache_key = f"stock:{sym}:{req_date_str}"

        if not bypass_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                self.last_meta = {
                    "cache": "hit",
                    "marketwatch_status": "skipped",
                    "mw_used_cookie": False,
                }
                return Stock.model_validate(cached)

        ohlc = self.polygon.get_ohlc(sym, req_date_str)

        mw, mw_status, mw_used_cookie = self._fetch_marketwatch(sym)

        purchased_amount = self._safe_get_amount(sym)
        purchased_status = "purchased" if purchased_amount > 0 else "not_purchased"

        performance_raw: dict[str, Any] = mw.get("performance") or {}
        competitors_raw: list[dict[str, Any]] = mw.get("competitors") or []
        company_name = mw.get("company_name") or sym

        def _to_float_or_none(v: Any) -> float | None:
            try:
                return float(v) if v is not None else None
            except Exception:
                return None

        stock = Stock(
            status=str(ohlc.get("status", "ok")),
            purchased_amount=float(purchased_amount),
            purchased_status=purchased_status,
            request_data=self._to_date(req_date_str),
            company_code=sym,
            company_name=company_name,
            Stock_values=StockValues(
                open=float(ohlc["open"]),
                high=float(ohlc["high"]),
                low=float(ohlc["low"]),
                close=float(ohlc["close"]),
                volume=_to_float_or_none(ohlc.get("volume")),
                afterHours=_to_float_or_none(ohlc.get("afterHours")),
                preMarket=_to_float_or_none(ohlc.get("preMarket")),
            ),
            performance_data=PerformanceData(
                five_days=to_float_or_zero(performance_raw.get("five_days")),
                one_month=to_float_or_zero(performance_raw.get("one_month")),
                three_months=to_float_or_zero(performance_raw.get("three_months")),
                year_to_date=to_float_or_zero(performance_raw.get("year_to_date")),
                one_year=to_float_or_zero(performance_raw.get("one_year")),
            ),
            Competitors=self._map_competitors(competitors_raw),
        )

        self.last_meta = {
            "cache": "bypass" if bypass_cache else "miss",
            "marketwatch_status": mw_status,
            "mw_used_cookie": bool(mw_used_cookie),
        }

        if not bypass_cache:
            self._cache_set(cache_key, stock.model_dump(mode="json", by_alias=True))
        return stock

    def _fetch_marketwatch(self, sym: str) -> tuple[dict[str, Any], str, bool]:
        try:
            data = self.marketwatch.get_overview(sym, use_cookie=True)
            return data, "ok", True
        except Exception:
            try:
                data = self.marketwatch.get_overview(sym, use_cookie=False)
                return data, "ok", False
            except Exception:
                return {"company_name": sym, "performance": {}, "competitors": []}, "fallback", False

    def _map_competitors(self, items: list[dict[str, Any]]) -> list[Competitor]:
        result: list[Competitor] = []
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
                result.append(Competitor(name=str(name).strip(), market_cap=MarketCap(Currency=str(cur), Value=val_f)))
        return result

    def _resolve_request_date_str(self, d: str | date | None) -> str:
        if d is None:
            return IsoDate.from_any(last_business_day()).value
        return IsoDate.from_any(d).value

    def _to_date(self, s: str) -> date:
        return date.fromisoformat(s)

    def _safe_get_amount(self, symbol: str) -> int:
        if self.repo is None:
            return 0
        try:
            return int(self.repo.get_purchased_amount(symbol))
        except Exception:
            return 0
