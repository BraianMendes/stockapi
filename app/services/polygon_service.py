from datetime import date
from typing import Any

from ..utils import (
    Config,
    EnvConfig,
    HttpClient,
    HttpClientFactory,
    IsoDate,
    PolygonError,
    Symbol,
    polygon_map_http_error,
    to_float_or_none,
)


class PolygonService:
    """Client for Polygon Daily Open/Close (OHLC)."""

    def __init__(
        self,
        http: HttpClient | None = None,
        config: Config | None = None,
        base_url: str = "https://api.polygon.io/v1/open-close",
    ) -> None:
        self.http = http or HttpClientFactory.default()
        self.cfg = config or EnvConfig()
        self.base_url = self.cfg.get_str("POLYGON_BASE_URL", base_url)

    def get_ohlc(self, symbol: str, data_date: str | date) -> dict[str, Any]:
        """Returns normalized OHLC for a symbol/date."""
        try:
            api_key = self.cfg.get_str_required("POLYGON_API_KEY")
        except Exception:
            raise PolygonError("missing_api_key")

        adjusted = "true" if self.cfg.get_bool("POLYGON_ADJUSTED", True) else "false"
        timeout = self.cfg.get_float("HTTP_TIMEOUT", 15.0)

        sym = Symbol.of(symbol).value
        ds = IsoDate.from_any(data_date).value
        url = f"{self.base_url}/{sym}/{ds}"
        params = {"adjusted": adjusted, "apiKey": api_key}

        try:
            payload = self.http.get_json(url, headers=None, params=params, timeout=timeout)
        except Exception as e:
            raise polygon_map_http_error(e)

        open_v = payload.get("open")
        high_v = payload.get("high")
        low_v = payload.get("low")
        close_v = payload.get("close")

        if open_v is None or high_v is None or low_v is None or close_v is None:
            raise PolygonError("missing_ohlc_fields")

        result: dict[str, Any] = {
            "status": payload.get("status") or "ok",
            "symbol": payload.get("symbol") or payload.get("ticker") or sym,
            "request_date": ds,
            "open": float(open_v),
            "high": float(high_v),
            "low": float(low_v),
            "close": float(close_v),
        }

        volume_v = to_float_or_none(payload.get("volume"))
        if volume_v is not None:
            result["volume"] = volume_v

        after_hours_v = to_float_or_none(payload.get("afterHours"))
        if after_hours_v is not None:
            result["afterHours"] = after_hours_v

        pre_market_v = to_float_or_none(payload.get("preMarket"))
        if pre_market_v is not None:
            result["preMarket"] = pre_market_v

        return result