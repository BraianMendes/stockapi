import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup, FeatureNotFound

from ..domain import CompetitorsParserPort, PerformanceParserPort
from ..integrations.marketwatch import CompetitorsParser, PerformanceParser
from ..utils import (
    Config,
    EnvConfig,
    HttpClient,
    HttpClientFactory,
    ScraperError,
    Symbol,
    build_browser_headers,
    get_logger,
    random_user_agent,
)

MARKETWATCH_BASE_URL = "https://www.marketwatch.com/investing/stock"


class MarketWatchService:
    """Scrapes MarketWatch; delegates parsing to ports-based adapters."""

    USER_AGENTS = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    )

    def __init__(
        self,
        http: HttpClient | None = None,
        config: Config | None = None,
        base_url: str = MARKETWATCH_BASE_URL,
        *,
        cache_ttl_seconds: int | None = None,
        performance_parser: PerformanceParserPort | None = None,
        competitors_parser: CompetitorsParserPort | None = None,
    ) -> None:
        self.http = http or HttpClientFactory.default()
        self.cfg = config or EnvConfig()
        self.base_url = base_url
        self.log = get_logger("app.services.marketwatch")

        self._perf_parser: PerformanceParserPort = performance_parser or PerformanceParser()
        self._comp_parser: CompetitorsParserPort = competitors_parser or CompetitorsParser()

        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_exp: dict[str, datetime] = {}
        ttl_default = 60
        try:
            ttl_default = int(self.cfg.get_int("MW_LOCAL_CACHE_TTL", ttl_default))
        except Exception:
            pass
        self._cache_ttl = int(cache_ttl_seconds if cache_ttl_seconds is not None else ttl_default)

    def _ascii_snippet(self, text: str, max_len: int) -> str:
        s = (text or "")[:max_len]
        return s.encode("ascii", "ignore").decode("ascii")

    def _cache_get(self, sym: str) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        exp = self._cache_exp.get(sym)
        if exp and exp > now:
            cached = self._cache.get(sym)
            if cached:
                return cached
        if exp and exp <= now:
            self._cache_exp.pop(sym, None)
            self._cache.pop(sym, None)
        return None

    def _cache_set(self, sym: str, data: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        self._cache[sym] = data
        self._cache_exp[sym] = now + timedelta(seconds=self._cache_ttl)

    def get_overview(self, symbol: str, *, use_cookie: bool = True) -> dict[str, Any]:
        sym = Symbol.of(symbol).value

        cached = self._cache_get(sym)
        if cached:
            return cached

        url = f"{self.base_url}/{sym.lower()}"
        headers = self._build_headers(use_cookie=use_cookie)
        try:
            timeout = float(self.cfg.get_float("HTTP_TIMEOUT", 15.0))
        except Exception:
            timeout = 15.0

        html = self._fetch_html(url, headers=headers, timeout=timeout)
        try:
            soup = BeautifulSoup(html, "lxml")
        except FeatureNotFound:
            soup = BeautifulSoup(html, "html.parser")

        company_name = self._extract_company_name(soup) or sym
        performance = self._perf_parser.parse(soup)
        competitors = self._comp_parser.parse(soup, base_url="https://www.marketwatch.com")

        data = {
            "company_code": sym,
            "company_name": company_name,
            "performance": performance,
            "competitors": competitors,
            "source": "marketwatch",
            "url": url,
        }

        self._cache_set(sym, data)
        return data

    def _fetch_html(self, url: str, headers: dict[str, str], timeout: float) -> str:
        try:
            jitter_min = float(self.cfg.get_float("MW_JITTER_MIN", 0.8))
            jitter_max_opt = self.cfg.get_float("MW_JITTER_MAX", 2.2)
            jitter_max = float(jitter_max_opt)
        except Exception:
            jitter_min, jitter_max = 0.8, 2.2
        time.sleep(random.uniform(jitter_min, jitter_max))

        session_get = getattr(getattr(self.http, "session", None), "get", None)
        if not callable(session_get):
            raise ScraperError("http_client_missing_raw_get")

        start = time.perf_counter()
        try:
            r = session_get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            html = r.text or ""
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            try:
                snippet_len = int(self.cfg.get_int("MW_HTML_PREVIEW_LEN", 200))
            except Exception:
                snippet_len = 200
            snippet = self._ascii_snippet(html, snippet_len)
            self.log.info(
                "marketwatch_fetch_ok",
                extra={"url": url, "status": getattr(r, "status_code", None), "ms": elapsed_ms, "preview": snippet},
            )
            return html
        except requests.HTTPError as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status = getattr(getattr(e, "response", None), "status_code", None)
            text = getattr(getattr(e, "response", None), "text", "") or ""
            try:
                snippet_len = int(self.cfg.get_int("MW_HTML_PREVIEW_LEN", 200))
            except Exception:
                snippet_len = 200
            snippet = self._ascii_snippet(text, snippet_len)
            self.log.warning(
                "marketwatch_fetch_blocked",
                extra={"url": url, "status": status, "ms": elapsed_ms, "preview": snippet},
            )
            msg = f"blocked:{status}" if status in (401, 403) else f"http_error:{status}"
            raise ScraperError(msg)
        except requests.RequestException as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.log.warning(
                "marketwatch_fetch_error",
                extra={"url": url, "ms": elapsed_ms, "error": str(e)[:120]},
            )
            self.log.debug("marketwatch_fetch_exc", extra={"url": url}, exc_info=True)
            raise ScraperError(f"error:{str(e)[:80]}")
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.log.warning(
                "marketwatch_fetch_error",
                extra={"url": url, "ms": elapsed_ms, "error": str(e)[:120]},
            )
            self.log.debug("marketwatch_fetch_exc_unexpected", extra={"url": url}, exc_info=True)
            raise ScraperError(f"error:{str(e)[:80]}")

    def _build_headers(self, *, use_cookie: bool = True) -> dict[str, str]:
        cookie_opt = self.cfg.get_str("MARKETWATCH_COOKIE", "") if use_cookie else ""
        cookie = cookie_opt or ""
        ua = random_user_agent(self.USER_AGENTS)
        return build_browser_headers(ua, cookie if cookie else None)

    def _extract_company_name(self, soup: BeautifulSoup) -> str | None:
        try:
            meta = soup.select_one("meta[property='og:title']")
            content_val = meta.get("content") if meta is not None else None
            if content_val:
                t = str(content_val).strip()
                if t:
                    return t.split(" - ")[0].strip() or None
        except Exception:
            pass

        for sel in ("[data-module='Quote'] h1", "h1.company__name", "h1", "[data-automation-id='quote-header'] h1"):
            try:
                el = soup.select_one(sel)
            except Exception:
                continue
            if el:
                try:
                    name = el.get_text(strip=True)
                except Exception:
                    name = None
                if name:
                    return name
        title_text: str | None = None
        try:
            title_tag = getattr(soup, "title", None)
            if title_tag is not None:
                title_str = getattr(title_tag, "string", None)
                if title_str is not None:
                    title_text = title_str.strip()
        except Exception:
            title_text = None
        if title_text:
            try:
                return title_text.split(" - ")[0].strip() or None
            except Exception:
                pass
        return None