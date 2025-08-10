from datetime import datetime, date, timedelta, UTC
from typing import Dict, Any
from fastapi import APIRouter
from ..services import PolygonService, MarketWatchService
from ..utils import EnvConfig, PolygonError, ScraperError

router = APIRouter(tags=["Health"])

cfg = EnvConfig()
polygon_svc = PolygonService()
mw_svc = MarketWatchService()


def last_trading_date(start: date | None = None) -> date:
    """
    Return the last business day before `start` (or today).
    """
    d = (start or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def check_polygon() -> str:
    """
    Verify Polygon Daily Open/Close by fetching OHLC for AAPL.
    """
    try:
        _ = polygon_svc.get_ohlc("AAPL", last_trading_date())
        return "ok"
    except PolygonError as e:
        msg = str(e).lower()
        if "missing" in msg and "key" in msg:
            return "missing_api_key"
        if "rate" in msg and "limit" in msg:
            return "rate_limited"
        return f"error:{msg}"
    except Exception as e:
        return f"error:{str(e)[:60]}"


def check_marketwatch() -> str:
    """
    Verify MarketWatch scraping by fetching overview for AAPL.
    Accept partial responses as healthy enough for readiness.
    Cookie strategy: try without cookie first; if blocked (401/403), try again with env cookie.
    """
    try:
        data = mw_svc.get_overview("AAPL", use_cookie=False)
        perf = data.get("performance") or {}
        competitors = data.get("competitors") or []
        has_any_perf = any(perf.get(k) is not None for k in ("five_days", "one_month", "three_months", "year_to_date", "one_year"))
        if has_any_perf or len(competitors) > 0:
            return "ok"
        return "ok_basic"
    except ScraperError as e:
        msg = str(e)
        if msg.startswith("blocked:"):
            try:
                data = mw_svc.get_overview("AAPL", use_cookie=True)
                perf = data.get("performance") or {}
                competitors = data.get("competitors") or []
                has_any_perf = any(perf.get(k) is not None for k in ("five_days", "one_month", "three_months", "year_to_date", "one_year"))
                if has_any_perf or len(competitors) > 0:
                    return "ok"
                return "ok_basic"
            except ScraperError as e2:
                return f"error:{str(e2)[:60]}"
        return f"error:{msg[:60]}"
    except Exception as e:
        return f"error:{str(e)[:60]}"


@router.get("/health", summary="Liveness probe")
def health() -> Dict[str, Any]:
    """
    Process up and running.
    """
    return {
        "status": "ok",
        "service": "stocks-api",
        "time": datetime.now(UTC).isoformat(),
    }


@router.get("/ready", summary="Readiness probe")
def readiness() -> Dict[str, Any]:
    """
    Verify external dependencies (Polygon and MarketWatch).
    """
    checks = {
        "polygon_api": check_polygon(),
        "marketwatch_api": check_marketwatch(),
    }

    polygon_ok = checks["polygon_api"] == "ok"
    marketwatch_ok = checks["marketwatch_api"] in {"ok", "ok_basic"}

    all_ok = polygon_ok and marketwatch_ok

    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
        "service_health": {
            "polygon": "healthy" if polygon_ok else "unhealthy",
            "marketwatch": "healthy" if marketwatch_ok else "unhealthy",
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/debug/env", summary="Debug environment")
def debug_env() -> Dict[str, Any]:
    """
    Show critical environment flags when DEBUG_ENV=true.
    """
    debug_enabled = (cfg.get_str("DEBUG_ENV", "false") or "false").lower() == "true"
    if not debug_enabled:
        return {"error": "Debug mode not enabled. Set DEBUG_ENV=true to use this endpoint."}

    polygon_key = cfg.get_str("POLYGON_API_KEY")
    mw_cookie = cfg.get_str("MARKETWATCH_COOKIE")

    return {
        "debug_info": {
            "polygon_api_key_present": bool(polygon_key),
            "polygon_api_key_length": len(polygon_key) if polygon_key else 0,
            "polygon_api_key_preview": polygon_key[:10] + "..." if polygon_key and len(polygon_key) > 10 else polygon_key,
            "marketwatch_cookie_present": bool(mw_cookie),
            "marketwatch_cookie_length": len(mw_cookie) if mw_cookie else 0,
        },
        "env_status": {
            "polygon": "configured" if polygon_key else "missing",
            "marketwatch": "configured" if mw_cookie else "missing",
        },
    }


@router.get("/ping", summary="Ping")
def ping() -> str:
    """
    Basic echo endpoint.
    """
    return "pong"