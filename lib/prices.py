"""yfinance price fetcher with parquet caching and delta-fetch.

Caches one parquet per ticker under data/cache/prices/{TICKER}.parquet. On
re-run, only fetches dates after the cached `last_date`.

`auto_adjust=True` so the `Close` column is total-return-adjusted (folds in
splits and dividends). For backtest purposes this is what we want.

Delisted tickers: yfinance returns price history up to delisting then NaN/empty
for later dates. We accept whatever it gives us; downstream code handles
"price not available on day X" by carrying forward the last close.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DIR = Path("data/cache/prices")
META_PATH = CACHE_DIR / "_meta.parquet"


def _load_meta() -> pd.DataFrame:
    if META_PATH.exists():
        return pd.read_parquet(META_PATH)
    return pd.DataFrame(columns=["ticker", "first_date", "last_date", "rows"])


def _save_meta(meta: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    meta.to_parquet(META_PATH, index=False)


def _cache_path(ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe}.parquet"


def _yf_history(ticker: str, start: str, end: str, retries: int = 3) -> pd.DataFrame | None:
    """One yfinance fetch with retry/backoff. Returns DataFrame or None on failure."""
    last_err = None
    for attempt in range(retries):
        try:
            t = yf.Ticker(ticker)
            df = t.history(start=start, end=end, auto_adjust=True, raise_errors=False)
            if df is None or df.empty:
                # Empty result is not an error — ticker might just not have data in window.
                return df if df is not None else pd.DataFrame()
            # Normalise the index to tz-naive dates
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            df = df[~df.index.duplicated(keep="last")]
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            last_err = e
            time.sleep(0.5 * (2**attempt))
    print(f"  [prices] {ticker}: yfinance failed after {retries} retries: {last_err}")
    return None


def fetch_prices(
    ticker: str,
    start: str,
    end: str,
    refresh: bool = False,
) -> pd.DataFrame | None:
    """Fetch OHLCV for ticker over [start, end], using cache where possible.

    Returns DataFrame indexed by date with columns Open/High/Low/Close/Volume,
    or None if yfinance has no data at all (truly unfetchable).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _cache_path(ticker)
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)

    if cache_path.exists() and not refresh:
        cached = pd.read_parquet(cache_path)
        cached.index = pd.to_datetime(cached.index)
        cached_first = cached.index.min() if not cached.empty else None
        cached_last = cached.index.max() if not cached.empty else None

        # If cache covers the requested window, return slice.
        if cached_first is not None and cached_first <= start_ts and cached_last >= end_ts:
            return cached.loc[start_ts:end_ts].copy()

        # Otherwise fetch the missing tail (most common case as data ages).
        if cached_last is not None and cached_last < end_ts:
            tail_start = (cached_last + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            tail = _yf_history(ticker, tail_start, end)
            if tail is not None and not tail.empty:
                cached = pd.concat([cached, tail])
                cached = cached[~cached.index.duplicated(keep="last")].sort_index()
                cached.to_parquet(cache_path)
        return cached.loc[start_ts:end_ts].copy() if not cached.empty else None

    # No cache (or refresh) — fresh fetch.
    df = _yf_history(ticker, start, end)
    if df is None:
        return None
    if df.empty:
        # Persist an empty marker so we don't repeatedly hit yfinance for
        # truly-missing tickers in subsequent runs.
        df.to_parquet(cache_path)
        return None
    df.to_parquet(cache_path)
    return df.loc[start_ts:end_ts].copy()


def trading_calendar(start: str, end: str) -> pd.DatetimeIndex:
    """Trading-day index over [start, end] derived from SPY price history."""
    spy = fetch_prices("SPY", start, end)
    if spy is None or spy.empty:
        raise RuntimeError("Could not fetch SPY for trading calendar")
    return pd.DatetimeIndex(sorted(spy.index.unique()))
