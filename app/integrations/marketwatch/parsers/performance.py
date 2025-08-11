"""
CA vertical slice adapter.
Implements the performance parsing port; swappable and isolated.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from bs4 import BeautifulSoup

from app.domain.ports import PerformanceParserPort
from app.utils import find_period_value, get_logger, parse_percent


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


class PerformanceParser(PerformanceParserPort):
    PERCENT_LOOSE_RE = re.compile(r"[-+]?\d+(?:[\.,]\d+)?\s*%")

    PERFORMANCE_ALIAS_SETS = {
        "five_days": {"5 d", "5 day", "5 days", "5d"},
        "one_month": {"1 m", "1 mo", "1 month", "one month", "1m"},
        "three_months": {"3 m", "3 mo", "3 month", "3 months", "three month", "three months", "3m"},
        "year_to_date": {"ytd", "year to date", "year to date %", "year to date (%)", "year to date percent"},
        "one_year": {"1 y", "1 yr", "1 year", "one year", "12 month", "12 months", "1y"},
    }

    def __init__(self, registry: SelectorRegistry | None = None) -> None:
        self.log = get_logger("app.parsers.performance")
        self._registry = registry or self._default_registry()
        self._perf_alias_map: dict[str, str] = {}
        for key, names in self.PERFORMANCE_ALIAS_SETS.items():
            for n in names:
                self._perf_alias_map[self._normalize_perf_label(n)] = key

    def _default_registry(self) -> SelectorRegistry:
        selectors = (
            "section[data-module='Performance']",
            "[data-module='QuotePerformance']",
            "[data-testid='performance']",
            "div[class*=performance]",
            "table[class*=performance]",
            "section:has(h2:-soup-icontains('performance'))",
            "div:has(h2:-soup-icontains('performance'))",
            "section:has(h3:-soup-icontains('performance'))",
            "div:has(h3:-soup-icontains('performance'))",
        )
        reg = SelectorRegistry([CssListHeuristic(list(selectors), label="performance")])
        return reg

    def parse(self, soup: BeautifulSoup) -> dict[str, float | None]:
        container, used_sel = self._registry.first(soup)
        scan_root = container or soup

        out: dict[str, float | None] = {k: None for k in self.PERFORMANCE_ALIAS_SETS.keys()}

        parent = scan_root.find_parent() if hasattr(scan_root, "find_parent") else None
        table = scan_root.select_one("table") or (parent.select_one("table") if parent else None)
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
                self.log.info("performance_parsed_table", extra={"selector": used_sel, "parsed": {k: v for k, v in out.items() if v is not None}})
                return out

        mapping = {
            "five_days": ["5D", "5 Day", "5 Days"],
            "one_month": ["1M", "1 Month", "1 Mo"],
            "three_months": ["3M", "3 Month", "3 Months", "3 Mo"],
            "year_to_date": ["YTD", "Year to Date"],
            "one_year": ["1Y", "1 Year", "12 Month", "12 Months"],
        }
        for key, labels in mapping.items():
            val = None
            for label in labels:
                v = find_period_value(scan_root, label, self.PERCENT_LOOSE_RE)
                if v:
                    val = parse_percent(v)
                    break
            out[key] = val

        self.log.info(
            "performance_parsed_scan",
            extra={"selector": used_sel, "any": any(v is not None for v in out.values()), "parsed": {k: v for k, v in out.items() if v is not None}},
        )
        return out

    def _normalize_perf_label(self, label: str) -> str:
        s = (label or "").strip().lower()
        s = re.sub(r"[\-_]+", " ", s)
        s = re.sub(r"[^a-z0-9 %]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    def _map_performance_label(self, label: str) -> str | None:
        s = self._normalize_perf_label(label)
        mapped = self._perf_alias_map.get(s)
        if mapped:
            return mapped
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
