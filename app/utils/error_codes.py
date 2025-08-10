from enum import Enum

class ErrorCode(str, Enum):
    """Centralized API error codes used in HTTP responses."""
    INVALID_SYMBOL = "invalid_symbol"

    POLYGON_UNAUTHORIZED = "polygon_unauthorized"
    POLYGON_RATE_LIMITED = "polygon_rate_limited"
    POLYGON_HTTP_ERROR = "polygon_http_error"

    UPSTREAM_ERROR = "upstream_error"
    PURCHASE_ERROR = "purchase_error"
