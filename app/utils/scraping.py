import re
from re import Pattern
from urllib.parse import urljoin


def safe_url_join(base_url: str, href: str | None) -> str | None:
    """Safely join a possibly relative href with a base URL.

    Returns the joined absolute URL, the original href if join fails, or None when href is falsy.
    """
    if not href:
        return None
    try:
        base = base_url if base_url.endswith("/") else base_url + "/"
        return urljoin(base, href)
    except Exception:
        return href


def find_value_by_siblings(container, lab_lower: str, percent_re: Pattern) -> str | None:
    try:
        elems = container.select("span, td, th, div, p, li, strong, b, em")
    except Exception:
        elems = []
    for idx, el in enumerate(elems):
        try:
            text = el.get_text(" ", strip=True)
        except Exception:
            continue
        if text.strip().lower() == lab_lower:
            sib = el.next_sibling
            while sib is not None:
                try:
                    if hasattr(sib, "get_text"):
                        val = sib.get_text(" ", strip=True)
                        if percent_re.search(val):
                            return val
                    else:
                        s = str(sib).strip()
                        if percent_re.search(s):
                            return s
                except Exception:
                    pass
                sib = getattr(sib, "next_sibling", None)
            if idx + 1 < len(elems):
                try:
                    val = elems[idx + 1].get_text(" ", strip=True)
                    if percent_re.search(val):
                        return val
                except Exception:
                    pass
    return None

def find_value_by_span_pairs(container, lab_lower: str, percent_re: Pattern) -> str | None:
    try:
        spans = container.find_all("span")
    except Exception:
        spans = []
    for i in range(len(spans) - 1):
        try:
            left = spans[i].get_text(" ", strip=True)
            if left.strip().lower() == lab_lower:
                right = spans[i + 1].get_text(" ", strip=True)
                if percent_re.search(right):
                    return right
        except Exception:
            continue
    return None

def find_value_by_regex(container, label: str) -> str | None:
    try:
        flat = container.get_text(" ", strip=True)
    except Exception:
        flat = ""
    pattern = re.compile(rf"(?i)\b{re.escape(label)}\b[^0-9%+-]{{0,40}}([-+]?\d+(?:[\.,]\d+)?\s*%)")
    m = pattern.search(flat)
    if m:
        return m.group(1)
    return None

def find_period_value(container, label: str, percent_re: Pattern) -> str | None:
    """Find the percent value next to a period label using 3 clear strategies."""
    if not container or not label:
        return None
    lab = label.strip()
    lab_lower = lab.lower()

    v = find_value_by_siblings(container, lab_lower, percent_re)
    if v:
        return v
    v = find_value_by_span_pairs(container, lab_lower, percent_re)
    if v:
        return v
    return find_value_by_regex(container, lab)


def extract_link_info(elem, base_url: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (name, url, href, aria_label) from the first relevant link inside elem."""
    link = elem.find("a", href=True) or elem.select_one("a[data-symbol], a[aria-label]")
    name = link.get_text(strip=True) if link else None
    href = link.get("href") if link else None
    aria = link.get("aria-label") if link else None
    url = None
    if href:
        url = href if href.startswith("http") else safe_url_join(base_url, href)
    return name, url, href, aria

def infer_symbol(elem, name: str | None, href: str | None, aria: str | None) -> str | None:
    sym_el = elem.select_one("a[data-symbol], a[data-ticker], .symbol, [data-symbol], [data-ticker]")
    data_sym = None
    if sym_el:
        data_sym = sym_el.get("data-symbol") or sym_el.get("data-ticker")
        if not data_sym:
            try:
                data_sym = sym_el.get_text(strip=True)
            except Exception:
                data_sym = None
    if data_sym:
        s = str(data_sym).strip().upper()
        if s:
            return s
    if aria:
        m = re.search(r"\b([A-Z]{1,10}(?:\.[A-Z]{1,5})?)\b", aria)
        if m:
            return m.group(1).upper()
    if href:
        m = re.search(r"/investing/stock/([A-Za-z0-9\.-]+)", href) or re.search(r"/quote/([A-Za-z0-9\.-]+)", href)
        if m:
            return m.group(1).upper()
    if name:
        m = re.search(r"\(([A-Z]{1,10}(?:\.[A-Z]{1,5})?)\)", name)
        if m:
            return m.group(1).upper()
    return None

def extract_mcap_from_table(elem) -> str | None:
    tr = elem if getattr(elem, "name", None) == "tr" else elem.find_parent("tr")
    if not tr or not tr.find_parent("table"):
        return None
    table = tr.find_parent("table")
    headers = getattr(table, "_mw_header_map", None)
    if headers is None:
        headers = {}
        ths = table.select("thead th") or table.select("tr th")
        for idx, th in enumerate(ths):
            key = th.get_text(" ", strip=True).lower()
            headers[key] = idx
        table._mw_header_map = headers
    mcap_idx = None
    for k, idx in headers.items():
        if "market cap" in k or k in {"mkt cap", "cap"}:
            mcap_idx = idx
            break
    if mcap_idx is not None:
        tds = tr.find_all(["td", "th"])
        if 0 <= mcap_idx < len(tds):
            return tds[mcap_idx].get_text(" ", strip=True)
    return None

def extract_mcap_inline(elem, mcap_inline_re: Pattern) -> str | None:
    text = elem.get_text(" | ", strip=True)
    m = mcap_inline_re.search(text)
    if m:
        return m.group(2)
    spans = elem.find_all("span")
    if spans:
        try:
            return spans[-1].get_text(strip=True)
        except Exception:
            return None
    return None
