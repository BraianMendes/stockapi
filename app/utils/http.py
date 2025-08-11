import random
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .errors import PolygonError


@dataclass(frozen=True)
class RetryPolicy:
    """Retry settings for HTTP requests."""
    total: int = 3
    backoff_factor: float = 0.5
    status_forcelist: tuple = (429, 500, 502, 503, 504)


class HttpClient(Protocol):
    """Minimal HTTP client interface."""
    def get_json(self, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        ...


class RequestsHttpClient:
    """requests.Session-based HttpClient with retry/backoff."""
    def __init__(self, retry: RetryPolicy, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retries = Retry(
            total=retry.total,
            backoff_factor=retry.backoff_factor,
            status_forcelist=list(retry.status_forcelist),
            allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_json(self, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        """Sends GET and returns parsed JSON (or {})."""
        t = timeout or self.timeout
        resp = self.session.get(url, headers=headers, params=params, timeout=t)
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            code = getattr(e.response, "status_code", None)
            msg = f"HTTPError {code}: {e}"
            raise requests.HTTPError(msg, response=e.response) from None
        return resp.json() if resp.content else {}


class HttpClientFactory:
    """Factory for creating HttpClient instances."""
    @staticmethod
    def default(timeout: float = 15.0) -> HttpClient:
        return RequestsHttpClient(RetryPolicy(), timeout)


def random_user_agent(candidates: Iterable[str]) -> str:
    lst = list(candidates)
    if not lst:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    return random.choice(lst)


def build_browser_headers(user_agent: str, cookie: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def polygon_map_http_error(e: Exception) -> PolygonError:
    msg = str(e).lower()
    if "missing" in msg and "key" in msg:
        return PolygonError("missing_api_key")
    if "401" in msg or "403" in msg or "unauthorized" in msg:
        return PolygonError("unauthorized")
    if "404" in msg or "not found" in msg:
        return PolygonError("not_found")
    if "429" in msg or "too many" in msg:
        return PolygonError("rate_limited")
    if any(code in msg for code in ("500", "502", "503", "504")):
        return PolygonError("http_error")
    return PolygonError(f"http_error:{str(e)[:80]}")