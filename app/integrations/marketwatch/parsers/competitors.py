"""
CA vertical slice adapter.
Implements the competitors parsing port; swappable and isolated.
"""

from __future__ import annotations

import re
from typing import Any, Protocol
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.domain.ports import CompetitorsParserPort
from app.utils import (
    extract_link_info,
    extract_mcap_from_table,
    extract_mcap_inline,
    get_logger,
    infer_symbol,
    parse_money,
    safe_url_join,
    to_float_or_zero,
)


class SelectorHeuristic(Protocol):
    def find(self, soup: BeautifulSoup) -> tuple[Any | None, str | None]: ...


class SelectorRegistry:
    def __init__(self, heuristics: list[SelectorHeuristic] | None = None) -> None:
        self._hs: list[SelectorHeuristic] = list(heuristics or [])

    def register(self, h: SelectorHeuristic) -> None:
        self._hs.append(h)

    def first(self, soup: BeautifulSoup) -> tuple[Any | None, str | None]:
        for h in self._hs:
            try:
                el, name = h.find(soup)
                if el is not None:
                    return el, name
            except Exception:
                continue
        return None, None


class CssListHeuristic:
    def __init__(self, selectors: list[str], label: str) -> None:
        self._selectors = selectors
        self._label = label

    def find(self, soup: BeautifulSoup) -> tuple[Any | None, str | None]:
        for sel in self._selectors:
            try:
                el = soup.select_one(sel)
                if el:
                    return el, f"css:{self._label}:{sel}"
            except Exception:
                continue
        return None, None


class TableAriaHeuristic:
    def find(self, soup: BeautifulSoup) -> tuple[Any | None, str | None]:
        try:
            for tbl in soup.find_all("table"):
                aria = (tbl.get("aria-label") or "").strip().lower()
                if "competitor" in aria:
                    return tbl, "table[aria-label*='competitors']"
        except Exception:
            pass
        return None, None


class CompetitorsParser(CompetitorsParserPort):
    STOCK_URL_DISALLOWED_PARTS = (
        "/index/",
        "/future/",
        "/futures/",
        "/crypto/",
        "/currency/",
        "/commodit",
        "/etf/",
    )
    STOCK_URL_ALLOWED_PREFIXES = (
        "/investing/stock/",
        "/quote/",
    )
    ALLOWED_HOST_SUFFIX = "marketwatch.com"
    MCAP_INLINE_RE = re.compile(
        r"(Market\s*Cap|Mkt\s*Cap|Cap)\s*[:|\-]?\s*([$£€]?\s*[\d\.,]+\s*[KMBTkmbt]?)",
        flags=re.IGNORECASE,
    )

    def __init__(self, registry: SelectorRegistry | None = None) -> None:
        self.log = get_logger("app.parsers.competitors")
        self._registry = registry or self._default_registry()

    def _default_registry(self) -> SelectorRegistry:
        selectors = (
            "[data-module='Competitors']",
            "[data-testid='competitors']",
            "[data-testid='peers']",
            "[data-test='component-peers']",
            "section[data-module='Peers']",
            "section[data-module*='Peer']",
            "[data-module='QuotePeers']",
            "[data-module*='PeerTable']",
            ".peers",
            ".element--peers",
            ".Competitors",
            ".element.element--table.Competitors",
            "table[aria-label*='Competitors']",
            "section:has(h2:-soup-icontains('competitors'))",
            "div:has(h2:-soup-icontains('competitors'))",
            "section:has(h3:-soup-icontains('competitors'))",
            "div:has(h3:-soup-icontains('competitors'))",
            "section:has(h2:-soup-icontains('peers'))",
            "div:has(h2:-soup-icontains('peers'))",
            "section:has(h3:-soup-icontains('peers'))",
            "div:has(h3:-soup-icontains('peers'))",
        )
        reg = SelectorRegistry([CssListHeuristic(list(selectors), label="competitors"), TableAriaHeuristic()])
        return reg

    def parse(self, soup: BeautifulSoup, *, base_url: str) -> list[dict[str, Any]]:
        container, used_selector = self._registry.first(soup)
        if not container:
            title_text: str | None = None
            try:
                title_tag = getattr(soup, "title", None)
                if title_tag is not None:
                    title_str = getattr(title_tag, "string", None)
                    if title_str is not None:
                        title_text = title_str.strip()
            except Exception:
                title_text = None
            self.log.info("competitors_container_not_found", extra={"title": title_text})
            container = soup
            used_selector = "document_fallback"

        items = self._rows_from_container(container) or self._find_competitor_items(container)

        out: list[dict[str, Any]] = []
        blacklist_names = {"dow", "s&p 500", "nasdaq", "vix", "gold"}
        for it in items:
            name, symbol, url, mcap_text = self._extract_competitor_fields(it, base_url)

            name_lc = (name or "").strip().lower()
            if name_lc in blacklist_names:
                continue

            if not (symbol or self._looks_like_stock_url(url)):
                continue

            currency_value = parse_money(mcap_text) if mcap_text else None
            market_cap = None
            if currency_value:
                market_cap = {"currency": currency_value[0], "value": to_float_or_zero(currency_value[1])}
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

    def _rows_from_container(self, container) -> list:
        table = container if getattr(container, "name", "").lower() == "table" else container.select_one("table")
        if table:
            return table.select("tbody tr") or table.select("tr")
        return []

    def _find_competitor_items(self, container) -> list:
        comp_table = self._find_competitors_table(container)
        if comp_table:
            rows = comp_table.select("tbody tr") or comp_table.select("tr")
            if rows:
                return rows
        selectors = (
            "tbody tr",
            "tr",
            "ul li",
            "li",
            "div[class*=row]",
            "div[class*=table__row]",
            "a[data-symbol]",
            "a[aria-label*='Quote']",
            "a[href*='/investing/stock/']",
            "a[href*='/quote/']",
        )
        for sel in selectors:
            elems = container.select(sel)
            if elems and len(elems) >= 1:
                return elems
        return container.find_all(True, recursive=False)

    def _find_competitors_table(self, root) -> Any | None:
        try:
            for tbl in root.find_all("table"):
                aria = (tbl.get("aria-label") or "").strip().lower()
                if "competitor" in aria:
                    return tbl
        except Exception:
            pass
        return None

    def _extract_competitor_fields(self, elem, base_url: str) -> tuple[str | None, str | None, str | None, str | None]:
        name, url, href, aria = extract_link_info(elem, base_url)
        symbol = infer_symbol(elem, name, href, aria)
        sanitized_url = self._sanitize_stock_url(base_url, url or href)
        mcap_text = extract_mcap_from_table(elem) or extract_mcap_inline(elem, self.MCAP_INLINE_RE)
        return name, symbol, sanitized_url, mcap_text

    def _sanitize_stock_url(self, base_url: str, href_or_url: str | None) -> str | None:
        if not href_or_url:
            return None
        try:
            abs_url = href_or_url if href_or_url.startswith("http") else safe_url_join(base_url, href_or_url)
            if not abs_url:
                return None
            p = urlparse(abs_url)
            if p.scheme not in ("http", "https"):
                return None
            host = (p.hostname or p.netloc or "").lower()
            if not host.endswith(self.ALLOWED_HOST_SUFFIX):
                return None
            path_lc = (p.path or "").lower()
            if not any(path_lc.startswith(pref) for pref in self.STOCK_URL_ALLOWED_PREFIXES):
                return None
            if any(bad in path_lc for bad in self.STOCK_URL_DISALLOWED_PARTS):
                return None
            return abs_url
        except Exception:
            return None

    def _looks_like_stock_url(self, url: str | None) -> bool:
        if not url:
            return False
        try:
            p = urlparse(url)
            if p.scheme not in ("http", "https"):
                return False
            host = (p.hostname or p.netloc or "").lower()
            if not host.endswith(self.ALLOWED_HOST_SUFFIX):
                return False
            path_lc = (p.path or "").lower()
            if not any(path_lc.startswith(pref) for pref in self.STOCK_URL_ALLOWED_PREFIXES):
                return False
            if any(bad in path_lc for bad in self.STOCK_URL_DISALLOWED_PARTS):
                return False
            return True
        except Exception:
            return False
