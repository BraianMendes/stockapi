from enum import Enum


class ExternalServiceError(RuntimeError):
    """Base error for external services."""


class PolygonError(ExternalServiceError):
    """Polygon API error."""


class ScraperError(ExternalServiceError):
    """Scraping error."""


class ErrorCode(str, Enum):
    """API error codes."""
    INVALID_SYMBOL = "invalid_symbol"

    POLYGON_UNAUTHORIZED = "polygon_unauthorized"
    POLYGON_RATE_LIMITED = "polygon_rate_limited"
    POLYGON_HTTP_ERROR = "polygon_http_error"

    UPSTREAM_ERROR = "upstream_error"
    PURCHASE_ERROR = "purchase_error"

    INVALID_NON_BUSINESS_DATE = "invalid_non_business_date"
    MARKET_CLOSED = "market_closed"