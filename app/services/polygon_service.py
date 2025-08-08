from typing import Dict, Any, Optional, Union
from datetime import date
from ..utils import (
    HttpClient,
    HttpClientFactory,
    Config,
    EnvConfig,
    IsoDate,
    Symbol,
    PolygonError,
)


class PolygonService:
    """
    Polygon client that fetches and normalizes OHLC for a given symbol and date.
    """

    def __init__(
        self,
        http: Optional[HttpClient] = None,
        config: Optional[Config] = None,
        base_url: str = "https://api.polygon.io/v1/open-close",
    ) -> None:
        self.http = http or HttpClientFactory.default()
        self.cfg = config or EnvConfig()
        self.base_url = base_url

    def get_ohlc(self, symbol: str, data_date: Union[str, date]) -> Dict[str, Any]:
        """
        Return normalized OHLC for the symbol on the given date.
        """
        api_key = self.cfg.get_str_required("POLYGON_API_KEY")
        adjusted = "true" if self.cfg.get_bool("POLYGON_ADJUSTED", True) else "false"
        timeout = self.cfg.get_float("HTTP_TIMEOUT", 15.0)

        sym = Symbol.of(symbol).value
        ds = IsoDate.from_any(data_date).value
        url = f"{self.base_url}/{sym}/{ds}"
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"adjusted": adjusted}

        # Mapeia erros HTTP para PolygonError coerentes com o whiteboard
        try:
            payload = self.http.get_json(url, headers=headers, params=params, timeout=timeout)
        except Exception as e:
            msg = str(e).lower()
            # Heurística simples baseada na mensagem de requests
            if "401" in msg or "403" in msg:
                raise PolygonError("unauthorized")
            if "429" in msg or "too many" in msg:
                raise PolygonError("rate_limited")
            if any(code in msg for code in ("500", "502", "503", "504")):
                raise PolygonError("http_error")
            raise PolygonError(f"http_error:{str(e)[:80]}")

        open_v = payload.get("open")
        high_v = payload.get("high")
        low_v = payload.get("low")
        close_v = payload.get("close")

        if open_v is None or high_v is None or low_v is None or close_v is None:
            raise PolygonError("missing_ohlc_fields")

        return {
            "status": payload.get("status") or "ok",
            "symbol": payload.get("symbol") or payload.get("ticker") or sym,
            "request_date": ds,
            "open": float(open_v),
            "high": float(high_v),
            "low": float(low_v),
            "close": float(close_v),
        }


def get_stock_ohlc(symbol: str, data_date: Union[str, date]) -> Dict[str, Any]:
    """
    Convenience function using a default PolygonService instance.
    """
    return PolygonService().get_ohlc(symbol, data_date)