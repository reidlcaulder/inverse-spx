"""WRDS data layer — replaces fja05680 + yfinance + SEC EDGAR with CRSP + Compustat.

Why this is the gold standard:
  - CRSP `dsf` has ALL daily prices/shares/returns for delisted tickers, not just survivors
  - CRSP `dsedelist` provides explicit delisting return codes (e.g., -1.0 for bankruptcy)
    so the backtest doesn't silently censor wipe-outs
  - Compustat `idxcst_his` is the official S&P 500 constituent table with point-in-time
    from/thru dates (not a community CSV)
  - Returns from CRSP `ret` field are already total return (price + dividend)

Connection:
  Uses ~/.pgpass (created by `wrds.Connection(wrds_username=...)` interactive prompt).
  No password handling in code.

All large queries cache to data/cache/wrds_*.parquet. Re-runs are fast.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CACHE_DIR = Path("data/cache")
SP500_GVKEYX = "000003"  # S&P 500 Composite Index identifier in Compustat (idx_index conm = 'S&P 500 Comp-Ltd')


def get_connection(username: str | None = None):
    """Open a WRDS PostgreSQL connection. Requires ~/.pgpass to be set up.

    If `username` is None, reads WRDS_USERNAME from env / .env via lib.config.
    """
    import wrds  # imported here so users without WRDS don't need it installed
    from . import config
    user = username or config.wrds_username()
    if not user:
        raise RuntimeError(
            "WRDS_USERNAME not set. Add it to .env or pass --username, "
            "and ensure .pgpass is configured per WRDS docs."
        )
    return wrds.Connection(wrds_username=user)


# ------------------------- Stage 1: constituents -------------------------

def fetch_sp500_constituents(conn, start: str, end: str, refresh: bool = False) -> pd.DataFrame:
    """Long-format S&P 500 membership including historical exits.

    Reid's WRDS subscription has a critical limitation: `comp.idxcst_his`
    on this tier contains ONLY current S&P 500 members (~503 rows, all with
    null thru-date). Historical exits (Lehman, Sears, SVB, FRC, etc.) are
    absent. Using it as a membership source produces severe survivorship bias.

    Instead we use the fja05680/sp500 GitHub CSV for point-in-time membership
    (which includes exits via the -YYYYMM ticker suffix) and map historical
    tickers to CRSP permnos via crsp.msenames (which handles renames cleanly
    via the namedt/nameendt validity range).
    """
    cache_path = CACHE_DIR / "wrds_constituents.parquet"
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    # Step 1: point-in-time membership from fja05680 (includes historical exits)
    from . import constituents as fja
    history = fja.fetch_constituents_history()  # long-format date, ticker

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    pre_start = (start_ts - pd.offsets.QuarterEnd(1)).normalize()
    quarter_ends = pd.DatetimeIndex(
        [pre_start] + list(pd.date_range(start, end, freq="QE"))
    )

    # Build the union of all tickers ever in S&P 500 in the window
    all_tickers: set[str] = set()
    members_at: dict[pd.Timestamp, list[str]] = {}
    for d in quarter_ends:
        members = fja.constituents_at(d, history)
        members_at[d] = members
        all_tickers.update(members)

    # Step 2: bulk-pull msenames history for everything (one query)
    # Match by ticker (msenames.ticker) AND date validity (namedt/nameendt).
    tickers_csv = ",".join(f"'{t}'" for t in sorted(all_tickers))
    names = conn.raw_sql(
        f"""
        SELECT permno, ticker, ncusip,
               namedt::date AS namedt, nameendt::date AS nameendt,
               shrcd, exchcd
        FROM crsp.msenames
        WHERE ticker IN ({tickers_csv})
          AND shrcd IN (10, 11)  -- common stock only
          AND exchcd IN (1, 2, 3)  -- NYSE, AMEX, Nasdaq
        """
    )
    names["namedt"] = pd.to_datetime(names["namedt"])
    names["nameendt"] = pd.to_datetime(names["nameendt"])

    # Step 3: pre-build per-ticker validity ranges for O(R) lookup per date,
    # where R is the small number of name records for that ticker (usually 1-3).
    ticker_to_ranges: dict[str, list[tuple[pd.Timestamp, pd.Timestamp, int]]] = {}
    for _, row in names.iterrows():
        ticker_to_ranges.setdefault(row["ticker"], []).append(
            (row["namedt"], row["nameendt"], int(row["permno"]))
        )
    # Sort each ticker's ranges by start date, descending (most recent first)
    for t in ticker_to_ranges:
        ticker_to_ranges[t].sort(key=lambda r: r[0], reverse=True)

    rows = []
    missing_count = 0
    for d in quarter_ends:
        for ticker in members_at[d]:
            ranges = ticker_to_ranges.get(ticker, [])
            permno: int | None = None
            for namedt, nameendt, p in ranges:
                if namedt <= d <= nameendt:
                    permno = p
                    break
            if permno is None:
                missing_count += 1
                continue
            rows.append({
                "date": d.normalize(),
                "permno": permno,
                "ticker": ticker,
            })

    if missing_count:
        print(f"  [constituents] {missing_count} ticker-rebal pairs failed to map to a permno")

    df = pd.DataFrame(rows)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


# ------------------------- Stage 2: daily data -------------------------

def fetch_daily_data(
    conn, permnos: list[int], start: str, end: str, refresh: bool = False
) -> pd.DataFrame:
    """Daily prices, shares-out, returns for the given permnos.

    Returns DataFrame with columns: permno, date, price, shares, ret, retx, mc.
      price  = absolute value of CRSP prc (CRSP encodes midpoints as negatives)
      shares = shrout * 1000 (CRSP shrout is in thousands)
      ret    = total return (price + dividend)
      retx   = ex-dividend price return
      mc     = price * shares (point-in-time market cap)
    """
    cache_path = CACHE_DIR / "wrds_daily.parquet"
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    permno_csv = ",".join(map(str, permnos))
    df = conn.raw_sql(
        f"""
        SELECT permno, date::date AS date,
               ABS(prc) AS price,
               shrout::float * 1000 AS shares,
               ret, retx
        FROM crsp.dsf
        WHERE permno IN ({permno_csv})
          AND date BETWEEN '{start}'::date AND '{end}'::date
          AND prc IS NOT NULL
          AND shrout IS NOT NULL
        """
    )
    df["date"] = pd.to_datetime(df["date"])
    df["mc"] = df["price"] * df["shares"]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


def fetch_delistings(
    conn, permnos: list[int], start: str, end: str, refresh: bool = False
) -> pd.DataFrame:
    """Delisting events with delisting return code and value.

    dlstcd: delisting code (100 = active, 200-499 = merger/acquisition,
            500+ = liquidation/bankruptcy)
    dlret:  delisting return (e.g. -1.0 for full wipe-out)
    """
    cache_path = CACHE_DIR / "wrds_delistings.parquet"
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    permno_csv = ",".join(map(str, permnos))
    df = conn.raw_sql(
        f"""
        SELECT permno, dlstdt::date AS dlstdt, dlstcd, dlret
        FROM crsp.dsedelist
        WHERE permno IN ({permno_csv})
          AND dlstdt BETWEEN '{start}'::date AND '{end}'::date
        """
    )
    df["dlstdt"] = pd.to_datetime(df["dlstdt"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


def fetch_spy_total_return(conn, start: str, end: str, refresh: bool = False) -> pd.DataFrame:
    """SPY daily total return for benchmarking — from CRSP rather than yfinance.

    SPY's permno is 84398.
    """
    cache_path = CACHE_DIR / "wrds_spy.parquet"
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    df = conn.raw_sql(
        f"""
        SELECT date::date AS date, ret, ABS(prc) AS price
        FROM crsp.dsf
        WHERE permno = 84398
          AND date BETWEEN '{start}'::date AND '{end}'::date
          AND prc IS NOT NULL
        ORDER BY date
        """
    )
    df["date"] = pd.to_datetime(df["date"])
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df
