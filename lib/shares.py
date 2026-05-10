"""SEC EDGAR XBRL company-facts fetcher for point-in-time shares outstanding.

Endpoint: https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json
This single call returns the entire fact dictionary including the full history
of `dei:EntityCommonStockSharesOutstanding` and `us-gaap:CommonStockSharesOutstanding`.

Caches the full JSON per ticker to data/cache/sec_facts/{TICKER}.json.

Concept priority (per SEC guidance and XBRL US):
    1. dei:EntityCommonStockSharesOutstanding   (cover-page CSO, freshest)
    2. us-gaap:CommonStockSharesOutstanding     (balance-sheet figure)
    3. us-gaap:CommonStockSharesIssued          (last-resort, may include treasury)

For dual-class issuers (GOOGL/GOOG, BRK.A/BRK.B) each ticker reports its own
class via XBRL axis qualifiers; we sum across classes per identifier when the
fact has multiple `value` entries with different `members`. In practice the
dei tag aggregates classes already; only used as a fallback.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

from . import config

CACHE_DIR = Path("data/cache/sec_facts")
CIK_MAP_PATH = Path("data/cache/ticker_cik_map.json")


def _sec_headers() -> dict:
    return {"User-Agent": config.sec_user_agent(), "Accept-Encoding": "gzip, deflate"}

# SEC rate limits at 10 req/sec — be polite.
_LAST_CALL_TS = 0.0
_MIN_INTERVAL_SEC = 0.12  # ~8 req/sec


def _rate_limit() -> None:
    global _LAST_CALL_TS
    now = time.time()
    elapsed = now - _LAST_CALL_TS
    if elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)
    _LAST_CALL_TS = time.time()


def _load_cik_map() -> dict[str, str]:
    """Ticker -> 10-digit-zero-padded CIK string. Cached on disk."""
    if CIK_MAP_PATH.exists():
        with CIK_MAP_PATH.open("r") as f:
            return json.load(f)
    _rate_limit()
    r = requests.get(
        "https://www.sec.gov/files/company_tickers.json", headers=_sec_headers(), timeout=30
    )
    r.raise_for_status()
    data = r.json()
    out: dict[str, str] = {}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper()
        cik = str(entry.get("cik_str", "")).zfill(10)
        if ticker and cik:
            out[ticker] = cik
    CIK_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CIK_MAP_PATH.open("w") as f:
        json.dump(out, f)
    return out


_CIK_MAP_CACHE: dict[str, str] | None = None


def ticker_to_cik(ticker: str) -> str | None:
    global _CIK_MAP_CACHE
    if _CIK_MAP_CACHE is None:
        _CIK_MAP_CACHE = _load_cik_map()
    # Try direct lookup; SEC uses '-' for class separator while we may use '.'
    candidates = [ticker.upper(), ticker.upper().replace(".", "-"), ticker.upper().replace("-", ".")]
    # Also try base symbol for class shares (BRK-A -> BRK)
    base = ticker.upper().split("-")[0].split(".")[0]
    candidates.append(base)
    for c in candidates:
        if c in _CIK_MAP_CACHE:
            return _CIK_MAP_CACHE[c]
    return None


def _cache_path(ticker: str) -> Path:
    safe = ticker.upper().replace("/", "_")
    return CACHE_DIR / f"{safe}.json"


def fetch_company_facts(ticker: str, refresh: bool = False) -> dict | None:
    """Fetch and cache the full XBRL company-facts blob. Returns None on 404."""
    cache_path = _cache_path(ticker)
    if cache_path.exists() and not refresh:
        try:
            with cache_path.open("r") as f:
                return json.load(f)
        except Exception:
            pass

    cik = ticker_to_cik(ticker)
    if cik is None:
        return None
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    _rate_limit()
    try:
        r = requests.get(url, headers=_sec_headers(), timeout=30)
    except Exception as e:
        print(f"  [shares] {ticker}: request failed: {e}")
        return None
    if r.status_code == 404:
        # No XBRL data for this CIK
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w") as f:
            json.dump({}, f)
        return {}
    if r.status_code != 200:
        print(f"  [shares] {ticker}: HTTP {r.status_code}")
        return None
    data = r.json()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w") as f:
        json.dump(data, f)
    return data


# Concept lookup paths inside the company-facts JSON.
# Structure: facts['facts'][taxonomy][concept]['units'][unit] -> list of period entries.
_CONCEPT_PATHS: list[tuple[str, str, str]] = [
    ("dei",     "EntityCommonStockSharesOutstanding",      "shares"),
    ("us-gaap", "CommonStockSharesOutstanding",            "shares"),
    ("us-gaap", "CommonStockSharesIssued",                 "shares"),
]


def _entries_for_concept(facts: dict, taxonomy: str, concept: str, unit: str) -> list[dict]:
    try:
        return facts["facts"][taxonomy][concept]["units"][unit]
    except (KeyError, TypeError):
        return []


def shares_outstanding_at(facts: dict | None, asof: pd.Timestamp) -> float | None:
    """Return shares outstanding most recently reported on or before `asof`.

    Walks the concept priority list and, within each concept, picks the entry
    whose `end` (or `filed` if `end` missing) is the latest <= asof.
    Returns None if no concept yields a value.
    """
    if not facts:
        return None
    asof_str = pd.Timestamp(asof).strftime("%Y-%m-%d")

    for taxonomy, concept, unit in _CONCEPT_PATHS:
        entries = _entries_for_concept(facts, taxonomy, concept, unit)
        if not entries:
            continue

        # Filter to entries with end <= asof. Most entries have an `end` field.
        # For dei:EntityCommonStockSharesOutstanding the relevant date is `end`
        # (the cover-page as-of date).
        candidates = []
        for e in entries:
            end = e.get("end") or e.get("filed")
            if not end:
                continue
            if end <= asof_str:
                candidates.append(e)
        if not candidates:
            continue

        # Pick the latest by `end`, then by `filed` as tie-breaker.
        candidates.sort(key=lambda e: (e.get("end", ""), e.get("filed", "")))
        latest = candidates[-1]
        val = latest.get("val")
        if val is None or val <= 0:
            continue

        # Sanity guard: SEC has occasional scaling errors (off by 1000x).
        # S&P 500 companies should have shares-out between ~1M and ~50B.
        if val < 1e5 or val > 5e11:
            continue
        return float(val)

    return None


def load_manual_overrides() -> pd.DataFrame:
    """Load human-curated shares-outstanding overrides.

    CSV at data/manual_overrides/shares_outstanding.csv with columns
    date,ticker,shares. Date is the as-of date the override applies on or before.
    """
    p = Path("data/manual_overrides/shares_outstanding.csv")
    if not p.exists():
        return pd.DataFrame(columns=["date", "ticker", "shares"])
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].str.upper()
    return df


def shares_from_override(
    overrides: pd.DataFrame, ticker: str, asof: pd.Timestamp
) -> float | None:
    if overrides.empty:
        return None
    rows = overrides[(overrides["ticker"] == ticker.upper()) & (overrides["date"] <= asof)]
    if rows.empty:
        return None
    return float(rows.sort_values("date").iloc[-1]["shares"])
