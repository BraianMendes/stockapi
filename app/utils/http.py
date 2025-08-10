from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class RetryPolicy:
    """
    Retry strategy configuration.
    """
    total: int = 3
    backoff_factor: float = 0.5
    status_forcelist: tuple = (429, 500, 502, 503, 504)


class HttpClient(Protocol):
    """
    Minimal HTTP client interface for DI and testing.
    """
    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        ...


class RequestsHttpClient:
    """
    HttpClient based on requests.Session with retry/backoff.
    """
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

    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Send a GET request and return JSON or {}.
        """
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
    """
    Factory for configured HttpClient instances.
    """
    @staticmethod
    def default(timeout: float = 15.0) -> HttpClient:
        return RequestsHttpClient(RetryPolicy(), timeout)