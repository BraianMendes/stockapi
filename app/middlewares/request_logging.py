from __future__ import annotations

import time
from typing import Callable, Iterable, Optional, Set

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..utils import get_logger, set_trace_id, clear_trace_id


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs each request with a per-request trace_id, response status and latency.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        skip_paths: Optional[Iterable[str]] = None,
        header_trace_key: str = "X-Trace-Id",
    ) -> None:
        super().__init__(app)
        self.log = get_logger("app.middleware.request")
        self.header_trace_key = header_trace_key
        self.skip: Set[str] = set(skip_paths or (
            "/health", "/ready", "/docs", "/redoc", "/openapi.json"
        ))

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        skip = path in self.skip

        trace_id = set_trace_id()

        start = time.perf_counter()
        status_code = 500
        response: Optional[Response] = None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.log.exception(
                "unhandled exception",
                extra={
                    "method": request.method,
                    "path": path,
                    "status": status_code,
                    "ms": elapsed_ms,
                    "client": request.client.host if request.client else None,
                },
            )
            response = Response(status_code=status_code)
        finally:
            try:
                if response is not None:
                    response.headers[self.header_trace_key] = trace_id
            except Exception:
                pass

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        if not skip:
            self.log.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": path,
                    "query": str(request.url.query or ""),
                    "status": status_code,
                    "ms": elapsed_ms,
                    "client": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                    "content_length": request.headers.get("content-length"),
                },
            )

        clear_trace_id()

        return response
