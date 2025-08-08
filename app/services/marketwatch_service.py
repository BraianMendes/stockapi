from typing import Dict, Any, List, Optional, Tuple
from datetime import timedelta
import time
import random
import re
import requests
from bs4 import BeautifulSoup
from ..utils import (
    HttpClient,
    HttpClientFactory,
    Config,
    EnvConfig,
    Symbol,
    ScraperError,
    parse_percent,
    parse_money,
    get_logger,
)

MARKETWATCH_BASE_URL = "https://www.marketwatch.com/investing/stock"


class MarketWatchService:
    """
    Scrapes MarketWatch for company name, performance data, and competitors.
    """

    QUOTE_SELECTORS = [
        "[data-module='Quote']",
        ".intraday",
        ".region--intraday",
    ]

    PERFORMANCE_CONTAINER_SELECTORS = [
        "section[data-module='Performance']",
        "div[class*=performance]",
        "table[class*=performance]",
    ]

    COMPETITORS_CONTAINER_SELECTORS = [
        "[data-module='Competitors']",
        "[data-testid='competitors']",
        ".peers",
        ".element--peers",
    ]

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    ]

    def __init__(
        self,
        http: Optional[HttpClient] = None,
        config: Optional[Config] = None,
        base_url: str = MARKETWATCH_BASE_URL,
    ) -> None:
        self.http = http or HttpClientFactory.default()
        self.cfg = config or EnvConfig()
        self.base_url = base_url
        self.log = get_logger("app.services.marketwatch")

    def get_overview(self, symbol: str, *, use_cookie: bool = True) -> Dict[str, Any]:
        """
        Return company_name, performance_data, and competitors for a symbol.
        Set use_cookie=False to force a request without Cookie header.
        """
        sym = Symbol.of(symbol).value
        url = f"{self.base_url}/{sym.lower()}"
        headers = self._build_headers(use_cookie=use_cookie)
        timeout = self.cfg.get_float("HTTP_TIMEOUT", 15.0)

        html = self._fetch_html(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(html, "html.parser")

        company_name = self._extract_company_name(soup) or sym
        performance = self._extract_performance_data(soup)
        competitors = self._extract_competitors(soup, base_url="https://www.marketwatch.com")

        return {
            "company_code": sym,
            "company_name": company_name,
            "performance": performance,
            "competitors": competitors,
            "source": "marketwatch",
            "url": url,
        }

    def _fetch_html(self, url: str, headers: Dict[str, str], timeout: float) -> str:
        """
        Fetch HTML with basic jitter to reduce blocking. Wrap HTTP errors as ScraperError.
        """
        jitter_min = self.cfg.get_float("MW_JITTER_MIN", 0.8)
        jitter_max = self.cfg.get_float("MW_JITTER_MAX", 2.2)
        delay = random.uniform(jitter_min, jitter_max)
        time.sleep(delay)

        session_get = getattr(getattr(self.http, "session", None), "get", None)
        if not callable(session_get):
            raise ScraperError("http_client_missing_raw_get")

        start = time.perf_counter()
        try:
            r = session_get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            html = r.text or ""
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            snippet = (html[:200] or "").encode("ascii", "ignore").decode("ascii")
            self.log.info(
                "marketwatch_fetch_ok",
                extra={"url": url, "status": getattr(r, "status_code", None), "ms": elapsed_ms, "preview": snippet},
            )
            return html
        except requests.HTTPError as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status = getattr(getattr(e, "response", None), "status_code", None)
            text = getattr(getattr(e, "response", None), "text", "") or ""
            snippet = (text[:200]).encode("ascii", "ignore").decode("ascii")
            self.log.warning(
                "marketwatch_fetch_blocked",
                extra={"url": url, "status": status, "ms": elapsed_ms, "preview": snippet},
            )
            msg = f"blocked:{status}" if status in (401, 403) else f"http_error:{status}"
            raise ScraperError(msg)
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self.log.warning(
                "marketwatch_fetch_error",
                extra={"url": url, "ms": elapsed_ms, "error": str(e)[:120]},
            )
            raise ScraperError(f"error:{str(e)[:80]}")

    def _build_headers(self, *, use_cookie: bool = True) -> Dict[str, str]:
        """
        Build headers including optional Cookie from env.
        """
        cookie = self.cfg.get_str("MARKETWATCH_COOKIE", "") if use_cookie else ""
        ua = random.choice(self.USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
        }
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def _extract_company_name(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extract company name from header or quote module. Fallback to <title> prefix.
        """
        candidates = [
            "[data-module='Quote'] h1",
            "h1.company__name",
            "h1",
            "[data-automation-id='quote-header'] h1",
        ]
        for sel in candidates:
            el = soup.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                if name:
                    return name
        # Fallback: <title>
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            # Remove sufixos comuns após " - "
            return title.split(" - ")[0].strip() or None
        return None

    def _extract_performance_data(self, soup: BeautifulSoup) -> Dict[str, Optional[float]]:
        """
        Extract performance metrics mapped to assignment keys.
        """
        container = None
        for sel in self.PERFORMANCE_CONTAINER_SELECTORS:
            container = soup.select_one(sel)
            if container:
                break

        mapping = {
            "five_days": ["5D"],
            "one_month": ["1M"],
            "three_months": ["3M"],
            "year_to_date": ["YTD"],
            "one_year": ["1Y"],
        }

        out: Dict[str, Optional[float]] = {k: None for k in mapping.keys()}
        if not container:
            return out

        for key, labels in mapping.items():
            val = None
            for label in labels:
                v = self._find_period_value(container, label)
                if v:
                    val = parse_percent(v)
                    break
            out[key] = val
        return out

    def _find_period_value(self, container, label: str) -> Optional[str]:
        """
        Find performance value for a label like '5D', '1M', 'YTD', '1Y'.
        """
        node = container.find(string=re.compile(rf"\b{re.escape(label)}\b", re.IGNORECASE))
        if not node:
            return None
        parent = node.parent
        if not parent:
            return None
        nxt = parent.find_next_sibling()
        if not nxt:
            nxt = parent.find_parent().find_next_sibling() if parent.find_parent() else None
        return nxt.get_text(strip=True) if nxt else None

    def _extract_competitors(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """
        Extract up to five competitors with name, symbol, url and market_cap {currency, value}.
        """
        container = None
        for sel in self.COMPETITORS_CONTAINER_SELECTORS:
            container = soup.select_one(sel)
            if container:
                break
        if not container:
            return []

        items = self._find_competitor_items(container)
        out: List[Dict[str, Any]] = []
        for it in items:
            name, symbol, url, mcap_text = self._extract_competitor_fields(it, base_url)
            if not name and not symbol:
                continue
            currency_value = parse_money(mcap_text) if mcap_text else None
            market_cap = None
            if currency_value:
                market_cap = {"currency": currency_value[0], "value": float(currency_value[1])}
            out.append({
                "name": name or symbol,
                "symbol": symbol,
                "url": url,
                "market_cap": market_cap,
            })
            if len(out) >= 5:
                break
        return out

    def _find_competitor_items(self, container) -> List:
        """
        Find competitor row-like elements under container.
        """
        selectors = [
            "tr",
            "li",
            "div[class*=row]",
            "div[class*=table__row]",
        ]
        for sel in selectors:
            elems = container.select(sel)
            if elems and len(elems) >= 2:
                return elems
        return container.find_all(True, recursive=False)

    def _extract_competitor_fields(self, elem, base_url: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Extract competitor name, symbol, url, and market cap text from a row-like element.
        """
        link = elem.find("a", href=re.compile(r"/investing/stock/([A-Za-z0-9\.-]+)"))
        name = link.get_text(strip=True) if link else None
        symbol = None
        url = None
        if link and link.get("href"):
            href = link.get("href")
            url = href if href.startswith("http") else f"{base_url}{href}"
            m = re.search(r"/investing/stock/([A-Za-z0-9\.-]+)", href)
            if m:
                symbol = m.group(1).upper()

        mcap_text = None
        mcap_labels = ["Market Cap", "Mkt Cap", "Cap"]
        text = elem.get_text(" | ", strip=True)
        for lbl in mcap_labels:
            m = re.search(rf"{lbl}\s*[:|\-]?\s*([$\£\€]?\s*[\d\.,]+(?:[KMBTkmbt])?)", text, flags=re.IGNORECASE)
            if m:
                mcap_text = m.group(1)
                break
        if not mcap_text:
            spans = elem.find_all("span")
            if spans:
                mcap_text = spans[-1].get_text(strip=True)

        return name, symbol, url, mcap_text


def scrape_marketwatch(symbol: str) -> Dict[str, Any]:
    """
    Convenience function using default MarketWatchService.
    """
    return MarketWatchService().get_overview(symbol)