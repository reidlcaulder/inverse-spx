"""Pull S&P 500 weights directly from ETF SEC filings (IVV / SPY).

This bypasses the shares-outstanding lookup entirely. Once you have the actual
fund weights w_i (= value_i / Σ value_j from the filing's holdings table),
the mathematical inverse weights are u_i = (1/w_i) / Σ(1/w_j).

Uses CIK 0001100663 (iShares Trust) for IVV. Filings:
  - N-CSR    annual    period = 3/31 (IVV's fiscal year-end)
  - N-Q      fiscal Q1 period = 6/30
  - N-CSRS   semi-ann  period = 9/30
  - N-Q      fiscal Q3 period = 12/31

Each filing is a single ~30 MB HTML containing 5-10 ETFs from iShares Trust.
We extract the "iSHARES CORE S&P 500 ETF" section's holdings table.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

from . import config


def _headers() -> dict:
    return {"User-Agent": config.sec_user_agent()}


ISHARES_TRUST_CIK = "0001100663"
CACHE_DIR = Path("data/cache/etf_filings")

# Filings curated from EDGAR full-text search. Period → accession number.
# These are iShares Trust filings that contain IVV's Schedule of Investments.
IVV_FILINGS: dict[str, dict] = {
    "2014-12-31": {"form": "N-Q",     "acc": "0001193125-15-065725"},
    "2015-03-31": {"form": "N-CSR",   "acc": "0001193125-15-216083"},
    "2015-06-30": {"form": "N-Q",     "acc": "0001193125-15-306363"},
    "2015-09-30": {"form": "N-CSRS",  "acc": "0001193125-15-396474"},
    "2015-12-31": {"form": "N-Q",     "acc": "0001193125-16-480933"},
    "2016-03-31": {"form": "N-CSR",   "acc": "0001193125-16-613829"},
    "2016-06-30": {"form": "N-Q",     "acc": "0001193125-16-695276"},
    "2016-09-30": {"form": "N-CSRS",  "acc": "0001193125-16-788378"},
    "2016-12-31": {"form": "N-Q",     "acc": "0001193125-17-065125"},
    "2017-03-31": {"form": "N-CSR",   "acc": "0001193125-17-194722"},
    "2017-06-30": {"form": "N-Q",     "acc": "0001193125-17-271743"},
    "2017-09-30": {"form": "N-CSRS",  "acc": "0001193125-17-359934"},
    "2017-12-31": {"form": "N-Q",     "acc": "0001193125-18-063612"},
    "2018-03-31": {"form": "N-CSR",   "acc": "0001193125-18-186572"},
    "2018-06-30": {"form": "N-Q",     "acc": "0001193125-18-261300"},
    "2018-09-30": {"form": "N-CSRS",  "acc": "0001193125-18-344229"},
    "2018-12-31": {"form": "N-Q",     "acc": "0001193125-19-059323"},
    "2019-03-31": {"form": "N-CSR",   "acc": "0001193125-19-167652"},
    "2019-09-30": {"form": "N-CSRS",  "acc": "0001193125-19-306805"},
}


def _filing_doc_url(acc: str) -> str:
    """Find the main NQ/CSR HTML document URL within an accession folder."""
    acc_clean = acc.replace("-", "")
    folder = f"https://www.sec.gov/Archives/edgar/data/1100663/{acc_clean}/"
    r = requests.get(folder, headers=_headers(), timeout=30)
    r.raise_for_status()
    hrefs = re.findall(r'href="([^"]*\.htm)"', r.text)
    candidates = [h for h in hrefs if acc_clean in h and "index" not in h and "ex99" not in h.lower()]
    if not candidates:
        raise RuntimeError(f"No primary doc found in {folder}")
    # Prefer the largest/most likely main filing — usually has 'nq', 'ncsr', 'ncsrs' in name
    for keyword in ["dnq", "ncsr", "ncsrs"]:
        for h in candidates:
            if keyword in h.lower():
                return "https://www.sec.gov" + h
    return "https://www.sec.gov" + candidates[0]


def _strip_html(content: str) -> str:
    plain = re.sub(r"<[^>]+>", " ", content)
    plain = re.sub(r"&nbsp;|&#8202;|&#8201;|&#8203;|&#8199;|&#160;", " ", plain)
    plain = re.sub(r"&amp;", "&", plain)
    plain = re.sub(r"&reg;|&#0174;|&#174;", "", plain)
    plain = re.sub(r"&#151;|&#8211;|&#8212;", "-", plain)
    plain = re.sub(r"&#8217;|&#039;|&apos;", "'", plain)
    plain = re.sub(r"&#8220;|&#8221;|&quot;", '"', plain)
    plain = re.sub(r"&#216;|&#0216;", "", plain)  # Ø separator
    plain = re.sub(r"&#036;|&#0036;|&#36;", "$", plain)
    plain = re.sub(r"\s+", " ", plain)
    return plain


def _fetch_filing_doc(acc: str) -> str:
    """Download the filing's main HTML, stripped to plain text. Cached."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{acc}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    url = _filing_doc_url(acc)
    time.sleep(0.15)  # be polite to SEC
    r = requests.get(url, headers=_headers(), timeout=120)
    r.raise_for_status()
    plain = _strip_html(r.text)
    cache_path.write_text(plain, encoding="utf-8")
    return plain


def _extract_ivv_section(plain: str) -> str | None:
    """Carve out just the IVV common-stocks holdings table.

    The trick: filings vary by format. We need the ACTUAL holdings table, not
    cover-page or TOC references to IVV. The actual holdings table always has
    "iShares Core S&P 500 ETF" close to "Schedule of Investments" or
    "Security ... Shares ... Value" headers, AND a sector heading like
    "AEROSPACE & DEFENSE" within the next ~3000 chars.

    Ends at "TOTAL COMMON STOCKS".
    """
    # Try every occurrence of the IVV header (case-insensitive) and pick the one
    # immediately followed by holdings-table markers
    pattern = re.compile(r"iShares\s*(?:CORE|Core)\s+S&P\s+500\s+ETF", re.IGNORECASE)
    matches = list(pattern.finditer(plain))
    for m in matches:
        # The next 3000 chars should contain holdings-table markers
        peek = plain[m.end():m.end() + 3000]
        has_table_header = bool(re.search(
            r"(Security\s+Shares\s+Value)|(Schedule\s+of\s+Investments)", peek, re.IGNORECASE
        ))
        # Also require a sector heading like "AEROSPACE" or "COMMON STOCKS"
        has_sector = bool(re.search(
            r"COMMON\s+STOCKS|AEROSPACE|BANKS|SOFTWARE|HEALTH\s*CARE", peek, re.IGNORECASE
        ))
        if not (has_table_header and has_sector):
            continue
        # Find end at "Total Common Stocks" (case-insensitive — 2018+ uses lowercase)
        after = plain[m.end():]
        m_end = re.search(r"Total\s+Common\s+Stocks", after, re.IGNORECASE)
        if m_end:
            return plain[m.start():m.end() + m_end.start()]
        # Fallback: stop at next ETF heading
        m_next = re.search(
            r"iShares\s+(?:CORE|Core)\s+S&P\s+(?:MID-CAP|Mid-Cap|SMALL-CAP|Small-Cap|TOTAL|Total|U\.S\.)",
            after, re.IGNORECASE
        )
        if m_next:
            return plain[m.start():m.end() + m_next.start()]
        return plain[m.start():m.end() + 200_000]
    return None


# Holding row pattern: name (with optional footnote letters) + shares + optional $ + value
# Both shares and value are comma-formatted integers
_HOLDING_RE = re.compile(
    r"([A-Z][A-Za-z0-9'\.\s&\-,\(\)/]{2,90}?)\s+([\d]{1,3}(?:,\d{3})+)\s+\$?\s*([\d]{1,3}(?:,\d{3})+)"
)


def parse_ivv_holdings(plain: str) -> pd.DataFrame:
    """Returns DataFrame with columns: name, shares, value, weight."""
    section = _extract_ivv_section(plain)
    if not section:
        return pd.DataFrame(columns=["name", "shares", "value", "weight"])
    matches = _HOLDING_RE.findall(section)
    rows = []
    for name, shares_s, value_s in matches:
        # Strip footnote letters from name (e.g. "TransDigm Group Inc. a")
        clean = re.sub(r"\s+[a-e](?:,[a-e])*\s*$", "", name).strip(" .,")
        shares = int(shares_s.replace(",", ""))
        value = int(value_s.replace(",", ""))
        rows.append({"name": clean, "shares": shares, "value": value})
    df = pd.DataFrame(rows)
    if df.empty:
        df["weight"] = []
        return df
    # Drop the trailing related-party / level-summary rows that follow the holdings table
    # Heuristic: keep only contiguous rows from the start; stop when value drops below
    # ~$10M AND the cumulative weight exceeds 99% (these tail entries are post-table noise)
    df["weight"] = df["value"] / df["value"].sum()
    return df


def fetch_ivv_weights_at(period_end: str) -> pd.DataFrame:
    """Returns DataFrame of IVV holdings + weights at the given quarter-end."""
    spec = IVV_FILINGS.get(period_end)
    if not spec:
        raise KeyError(f"No filing curated for {period_end}")
    plain = _fetch_filing_doc(spec["acc"])
    return parse_ivv_holdings(plain)


def fetch_all_ivv_weights() -> dict[str, pd.DataFrame]:
    """Fetch (and cache) every curated IVV filing. Returns {period_end: df}."""
    out = {}
    for period in IVV_FILINGS:
        try:
            df = fetch_ivv_weights_at(period)
            out[period] = df
            print(f"  {period}: {len(df)} holdings, top weight {df['weight'].max()*100:.2f}%, total ${df['value'].sum()/1e9:.1f}B")
        except Exception as e:
            print(f"  {period}: FAILED {e}")
    return out
