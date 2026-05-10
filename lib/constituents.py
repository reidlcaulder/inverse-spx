"""S&P 500 historical constituents from the fja05680/sp500 GitHub repo.

The CSV has two columns: `date,tickers`. `tickers` is a comma-separated string
in one quoted field. Rows only exist on dates where membership changed; for any
arbitrary date, take the most recent row on or before that date.

Tickers that have left the index carry a `-YYYYMM` suffix (e.g. `AAMRQ-201312`).
We strip that suffix when looking up but keep it in the raw cache.

The repo has two CSVs:
  - `S&P 500 Historical Components & Changes.csv` — base file ending ~2019-01-11
  - `S&P 500 Historical Components & Changes(MM-DD-YYYY).csv` — dated, most-current

We always prefer the dated file. The filename rolls over periodically
(monthly-ish), so we use the GitHub API to find the latest one at runtime.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd
import requests

GITHUB_API = "https://api.github.com/repos/fja05680/sp500/contents/"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/fja05680/sp500/master/"

CACHE_PATH = Path("data/cache/constituents.parquet")


def _strip_delisted_suffix(ticker: str) -> str:
    """Strip the '-YYYYMM' suffix that fja05680 appends to delisted tickers."""
    return re.sub(r"-\d{6}$", "", ticker)


def _find_latest_dated_file() -> str | None:
    """List repo contents and return the download_url of the most-recently-dated CSV."""
    r = requests.get(GITHUB_API, timeout=30)
    r.raise_for_status()
    files = r.json()
    pattern = re.compile(r"S&P 500 Historical Components & Changes\((\d{2})-(\d{2})-(\d{4})\)\.csv")
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for f in files:
        name = f.get("name", "")
        m = pattern.match(name)
        if m:
            mm, dd, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            candidates.append(((yyyy, mm, dd), f["download_url"]))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _fetch_raw_csv() -> pd.DataFrame:
    """Hit the fja05680 raw CSV. Returns DataFrame with columns date, tickers (str).

    Prefers the latest dated file (which has the most-recent membership data).
    Falls back to the undated base file (which only goes through ~2019).
    """
    download_url = _find_latest_dated_file()
    if download_url:
        r = requests.get(download_url, timeout=30)
        if r.status_code == 200 and len(r.text) > 1000:
            return pd.read_csv(io.StringIO(r.text))

    # Fallback to the undated base file
    fallback_url = GITHUB_RAW_BASE + "S%26P%20500%20Historical%20Components%20%26%20Changes.csv"
    r = requests.get(fallback_url, timeout=30)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def fetch_constituents_history(refresh: bool = False) -> pd.DataFrame:
    """Long-format DataFrame with columns: date (datetime), ticker (str).

    Cached to data/cache/constituents.parquet. Pass refresh=True to re-fetch.
    """
    if CACHE_PATH.exists() and not refresh:
        return pd.read_parquet(CACHE_PATH)

    raw = _fetch_raw_csv()
    raw.columns = [c.strip().lower() for c in raw.columns]
    if "date" not in raw.columns or "tickers" not in raw.columns:
        raise RuntimeError(f"Unexpected CSV columns: {raw.columns.tolist()}")

    rows = []
    for _, r in raw.iterrows():
        d = pd.to_datetime(r["date"])
        for t in str(r["tickers"]).split(","):
            t = t.strip()
            if not t:
                continue
            rows.append({"date": d, "ticker": t})
    out = pd.DataFrame(rows)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(CACHE_PATH, index=False)
    return out


def constituents_at(asof: pd.Timestamp, history: pd.DataFrame) -> list[str]:
    """Return list of S&P 500 tickers as of `asof`.

    Forward-fills from the most recent membership snapshot on or before `asof`.
    Strips the `-YYYYMM` delisted-suffix from each ticker.
    """
    asof = pd.Timestamp(asof)
    snapshot_dates = history["date"].unique()
    snapshot_dates = sorted(d for d in snapshot_dates if d <= asof)
    if not snapshot_dates:
        return []
    latest = snapshot_dates[-1]
    rows = history[history["date"] == latest]
    return sorted({_strip_delisted_suffix(t) for t in rows["ticker"]})


def rebalance_dates(start: str, end: str, calendar: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Last trading day of each calendar quarter in [start, end].

    `calendar` is the full trading-day index (e.g. SPY's price index) so we
    never pick a non-trading date.
    """
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    cal = calendar[(calendar >= start_ts) & (calendar <= end_ts)]
    quarters = cal.to_series().groupby(cal.to_period("Q")).max()
    return [pd.Timestamp(d) for d in quarters.tolist()]
