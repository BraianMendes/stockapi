from typing import Any

from .config import Config, EnvConfig
from .dates import (
    is_business_day,
    last_business_day,
    next_business_day,
    previous_business_day,
    roll_to_business_day,
)
from .errors import ErrorCode, ExternalServiceError, PolygonError, ScraperError
from .http import (
    HttpClient,
    HttpClientFactory,
    RequestsHttpClient,
    RetryPolicy,
    build_browser_headers,
    polygon_map_http_error,
    random_user_agent,
)
from .logger import (
    JsonFormatter,
    PlainFormatter,
    TraceIdFilter,
    clear_trace_id,
    configure_logging,
    get_logger,
    set_trace_id,
)
from .parsing import (
    parse_money,
    parse_percent,
    to_float_or_none,
    to_float_or_zero,
)
from .scraping import (
    extract_link_info,
    extract_mcap_from_table,
    extract_mcap_inline,
    find_period_value,
    find_value_by_regex,
    find_value_by_siblings,
    find_value_by_span_pairs,
    infer_symbol,
    safe_url_join,
)
from .value_objects import IsoDate, Money, Percentage, Symbol

RedisCache: Any = None
try:
    from .redis_cache import RedisCache as _RedisCache  # type: ignore
    RedisCache = _RedisCache
except Exception:
    RedisCache = None

__all__ = [
    "Config",
    "EnvConfig",
    "HttpClient",
    "RequestsHttpClient",
    "HttpClientFactory",
    "RetryPolicy",
    "ExternalServiceError",
    "PolygonError",
    "ScraperError",
    "ErrorCode",
    "IsoDate",
    "Symbol",
    "Percentage",
    "Money",
    "parse_percent",
    "parse_money",
    "to_float_or_none",
    "to_float_or_zero",
    "configure_logging",
    "get_logger",
    "set_trace_id",
    "clear_trace_id",
    "JsonFormatter",
    "PlainFormatter",
    "TraceIdFilter",
    "build_browser_headers",
    "random_user_agent",
    "polygon_map_http_error",
    "last_business_day",
    "is_business_day",
    "previous_business_day",
    "next_business_day",
    "roll_to_business_day",
    "RedisCache",
    "safe_url_join",
    "find_value_by_siblings",
    "find_value_by_span_pairs",
    "find_value_by_regex",
    "find_period_value",
    "extract_link_info",
    "infer_symbol",
    "extract_mcap_from_table",
    "extract_mcap_inline",
]  # type: ignore
