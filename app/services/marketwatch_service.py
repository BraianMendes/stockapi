from typing import Dict, Any, List, Optional, Tuple
from datetime import timedelta, datetime, UTC
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

    PERFORMANCE_CONTAINER_SELECTORS = [
        "section[data-module='Performance']",
        "div[class*=performance]",
        "table[class*=performance]",
    ]

    COMPETITORS_CONTAINER_SELECTORS = [
        "[data-module='Competitors']",
        "[data-testid='competitors']",
        "[data-test='component-peers']",
        "section[data-module='Peers']",
        "section[data-module*='Peer']",
        "[data-module='QuotePeers']",
        "[data-module*='PeerTable']",
        ".peers",
        ".element--peers",
        "section:has(h2:-soup-icontains('competitors'))",
        "div:has(h2:-soup-icontains('competitors'))",
        "section:has(h3:-soup-icontains('competitors'))",
        "div:has(h3:-soup-icontains('competitors'))",
        "section:has(h2:-soup-icontains('peers'))",
        "div:has(h2:-soup-icontains('peers'))",
        "section:has(h3:-soup-icontains('peers'))",
        "div:has(h3:-soup-icontains('peers'))",
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
        *,
        cache_ttl_seconds: Optional[int] = None,
    ) -> None:
        self.http = http or HttpClientFactory.default()
        self.cfg = config or EnvConfig()
        self.base_url = base_url
        self.log = get_logger("app.services.marketwatch")

        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_exp: Dict[str, datetime] = {}
        self._cache_ttl = int(cache_ttl_seconds if cache_ttl_seconds is not None else self.cfg.get_int("MW_LOCAL_CACHE_TTL", 60))

    def get_overview(self, symbol: str, *, use_cookie: bool = True) -> Dict[str, Any]:
        """
        Return company_name, performance_data, and competitors for a symbol.
        Set use_cookie=False to force a request without Cookie header.
        """
        sym = Symbol.of(symbol).value

        now = datetime.now(UTC)
        exp = self._cache_exp.get(sym)
        if exp and exp > now:
            cached = self._cache.get(sym)
            if cached:
                return cached

        url = f"{self.base_url}/{sym.lower()}"
        headers = self._build_headers(use_cookie=use_cookie)
        timeout = self.cfg.get_float("HTTP_TIMEOUT", 15.0)

        html = self._fetch_html(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(html, "html.parser")

        company_name = self._extract_company_name(soup) or sym
        performance = self._extract_performance_data(soup)
        competitors = self._extract_competitors(soup, base_url="https://www.marketwatch.com")

        data = {
            "company_code": sym,
            "company_name": company_name,
            "performance": performance,
            "competitors": competitors,
            "source": "marketwatch",
            "url": url,
        }

        self._cache[sym] = data
        self._cache_exp[sym] = now + timedelta(seconds=self._cache_ttl)

        return data

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
            snippet_len = int(self.cfg.get_int("MW_HTML_PREVIEW_LEN", 200))
            snippet = (html[:snippet_len] or "").encode("ascii", "ignore").decode("ascii")
            self.log.info(
                "marketwatch_fetch_ok",
                extra={"url": url, "status": getattr(r, "status_code", None), "ms": elapsed_ms, "preview": snippet},
            )
            return html
        except requests.HTTPError as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status = getattr(getattr(e, "response", None), "status_code", None)
            text = getattr(getattr(e, "response", None), "text", "") or ""
            snippet_len = int(self.cfg.get_int("MW_HTML_PREVIEW_LEN", 200))
            snippet = (text[:snippet_len]).encode("ascii", "ignore").decode("ascii")
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
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            return title.split(" - ")[0].strip() or None
        return None

    def _normalize_perf_label(self, label: str) -> str:
        """Normalize label text for performance mapping (e.g., '5 Day' -> '5 day')."""
        s = label or ""
        s = s.strip().lower()
        s = re.sub(r"[\-_]+", " ", s)
        s = re.sub(r"[^a-z0-9 %]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _map_performance_label(self, label: str) -> Optional[str]:
        """Map various MW labels to our keys."""
        s = self._normalize_perf_label(label)
        aliases = {
            "five_days": {"5 d", "5 day", "5 days", "5d"},
            "one_month": {"1 m", "1 mo", "1 month", "one month", "1m"},
            "three_months": {"3 m", "3 mo", "3 month", "3 months", "three month", "three months", "3m"},
            "year_to_date": {"ytd", "year to date", "year to date %", "year to date (%)", "year to date percent"},
            "one_year": {"1 y", "1 yr", "1 year", "one year", "12 month", "12 months", "1y"},
        }
        for key, names in aliases.items():
            if s in names:
                return key
        if s.startswith("5 ") and "day" in s:
            return "five_days"
        if s.startswith("1 ") and ("month" in s or s.endswith("m")):
            return "one_month"
        if s.startswith("3 ") and ("month" in s or s.endswith("m")):
            return "three_months"
        if s.startswith("1 ") and ("year" in s or s.endswith("y")):
            return "one_year"
        if "ytd" in s or "year to date" in s:
            return "year_to_date"
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
            "five_days": ["5D", "5 Day", "5 Days"],
            "one_month": ["1M", "1 Month"],
            "three_months": ["3M", "3 Month", "3 Months"],
            "year_to_date": ["YTD", "Year to Date"],
            "one_year": ["1Y", "1 Year", "12 Month", "12 Months"],
        }

        out: Dict[str, Optional[float]] = {k: None for k in mapping.keys()}
        if not container:
            return out

        table = container.select_one("table") or container.find_parent().select_one("table") if hasattr(container, "find_parent") else None
        if table:
            rows = table.select("tbody tr") or table.select("tr")
            for tr in rows:
                cells = tr.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                label = cells[0].get_text(" ", strip=True)
                value_text = cells[1].get_text(" ", strip=True)
                key = self._map_performance_label(label)
                if key:
                    out[key] = parse_percent(value_text)
            if any(v is not None for v in out.values()):
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
        used_selector: Optional[str] = None
        for sel in self.COMPETITORS_CONTAINER_SELECTORS:
            try:
                el = soup.select_one(sel)
            except Exception as e:
                # Older SoupSieve versões podem não suportar algumas pseudo-classes (ex.: :-soup-icontains)
                self.log.debug("competitors_selector_error", extra={"selector": sel, "error": str(e)[:120]})
                continue
            if el:
                container = el
                used_selector = sel
                break
        if not container:
            container, used_selector = self._find_competitors_container_by_heading(soup)
        if not container:
            title = (soup.title.string.strip() if soup.title and soup.title.string else None)
            self.log.info("competitors_container_not_found", extra={"title": title})
            return []

        table = container.select_one("table")
        if table:
            items = table.select("tbody tr") or table.select("tr")
        else:
            items = self._find_competitor_items(container)

        out: List[Dict[str, Any]] = []
        blacklist_names = {"dow", "s&p 500", "nasdaq", "vix", "gold"}
        for it in items:
            name, symbol, url, mcap_text = self._extract_competitor_fields(it, base_url)

            name_lc = (name or "").strip().lower()
            if name_lc in blacklist_names:
                continue

            is_stock_url = False
            if url:
                u = url.lower()
                is_stock_url = ("/investing/stock/" in u or "/quote/" in u) and not any(x in u for x in ["/index/", "/future/", "/futures/", "/crypto/", "/currency/", "/commodit", "/etf/"])

            if not (symbol or is_stock_url):
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

        self.log.info(
            "competitors_parsed",
            extra={
                "selector": used_selector,
                "items_found": len(items) if items else 0,
                "parsed": len(out),
            },
        )
        return out

    def _find_competitors_container_by_heading(self, soup: BeautifulSoup) -> Tuple[Optional[Any], Optional[str]]:
        """Find a container by locating a heading with text 'Competitors' or 'Peers' and returning a relevant parent/sibling container."""
        headings = soup.select("h1, h2, h3, h4, h5")
        for h in headings:
            txt = h.get_text(" ", strip=True)
            if re.search(r"\b(competitors?|peers?)\b", txt, flags=re.IGNORECASE):
                sib = h.find_next_sibling()
                while sib and sib.name in {"script", "style"}:
                    sib = sib.find_next_sibling()
                if sib and (sib.name == "table" or sib.select_one("table")):
                    return (sib if sib.name == "table" else sib.select_one("table"), "heading+table")
                if sib and (sib.name == "ul" or sib.select_one("ul")):
                    return (sib if sib.name == "ul" else sib.select_one("ul"), "heading+ul")
                parent = h.find_parent(["section", "div"]) or h.parent
                if parent:
                    return (parent, "heading+parent")
        return (None, None)

    def _find_competitor_items(self, container) -> List:
        """
        Find competitor row-like elements under container.
        """
        selectors = [
            "tbody tr",
            "tr",
            "ul li",
            "li",
            "div[class*=row]",
            "div[class*=table__row]",
            "a[data-symbol]",
            "a[aria-label*='Quote']",
        ]
        for sel in selectors:
            elems = container.select(sel)
            if elems and len(elems) >= 1:
                return elems
        return container.find_all(True, recursive=False)

    def _extract_competitor_fields(self, elem, base_url: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Extract competitor name, symbol, url, and market cap text from a row-like element.
        """
        link = elem.find("a", href=True) or elem.select_one("a[data-symbol], a[aria-label]")
        name = link.get_text(strip=True) if link else None
        symbol = None
        url = None
        if link and link.get("href"):
            href = link.get("href")
            url = href if href.startswith("http") else f"{base_url}{href}"
            data_sym = link.get("data-symbol") or link.get("data-ticker")
            if data_sym:
                symbol = str(data_sym).strip().upper()
            if not symbol:
                aria = link.get("aria-label") or ""
                m = re.search(r"\b([A-Z]{1,10}(?:\.[A-Z]{1,5})?)\b", aria)
                if m:
                    symbol = m.group(1).upper()
            if not symbol:
                m = re.search(r"/investing/stock/([A-Za-z0-9\.-]+)", href) or re.search(r"/quote/([A-Za-z0-9\.-]+)", href)
                if m:
                    symbol = m.group(1).upper()

        if not symbol:
            sym_el = elem.select_one(".symbol, [data-symbol], [data-ticker]")
            if sym_el:
                symbol = (sym_el.get("data-symbol") or sym_el.get("data-ticker") or sym_el.get_text(strip=True) or "").upper()

        if not symbol and name:
            m = re.search(r"\(([A-Z]{1,10}(?:\.[A-Z]{1,5})?)\)", name)
            if m:
                symbol = m.group(1).upper()

        mcap_text: Optional[str] = None
        tr = elem if elem.name == "tr" else elem.find_parent("tr")
        if tr and tr.find_parent("table"):
            table = tr.find_parent("table")
            # Build header map once per table (cache in attribute)
            headers = getattr(table, "_mw_header_map", None)
            if headers is None:
                headers = {}
                ths = table.select("thead th") or table.select("tr th")
                for idx, th in enumerate(ths):
                    key = th.get_text(" ", strip=True).lower()
                    headers[key] = idx
                setattr(table, "_mw_header_map", headers)
            mcap_idx = None
            for k, idx in headers.items():
                if "market cap" in k or k in {"mkt cap", "cap"}:
                    mcap_idx = idx
                    break
            if mcap_idx is not None:
                tds = tr.find_all(["td", "th"])
                if 0 <= mcap_idx < len(tds):
                    mcap_text = tds[mcap_idx].get_text(" ", strip=True)
        if not mcap_text:
            text = elem.get_text(" | ", strip=True)
            m = re.search(r"(Market\s*Cap|Mkt\s*Cap|Cap)\s*[:|\-]?\s*([$£€]?\s*[\d\.,]+\s*[KMBTkmbt]?)", text, flags=re.IGNORECASE)
            if m:
                mcap_text = m.group(2)
        if not mcap_text:
            spans = elem.find_all("span")
            if spans:
                mcap_text = spans[-1].get_text(strip=True)

        return name, symbol, url, mcap_text