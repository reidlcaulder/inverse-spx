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
    """Long-format S&P 500 membership: rows are (date, permno, ticker).

    Reid's WRDS subscription doesn't include `crsp.dsp500list` or the CCM
    link table (`crsp_a_ccm.ccmxpf_lnkhist`). Instead we bridge:
      Compustat idxcst_his (gvkey)
        → comp.security (gvkey → CUSIP-9; take first 8 chars)
        → crsp.msenames (CUSIP-8 → permno)
    Both Compustat and CRSP use identical 8-char issue CUSIPs, so this works
    cleanly for vanilla US equities (which is everything in S&P 500).
    """
    cache_path = CACHE_DIR / "wrds_constituents.parquet"
    if cache_path.exists() and not refresh:
        return pd.read_parquet(cache_path)

    # Step 1: S&P 500 gvkey membership from Compustat
    members = conn.raw_sql(
        f"""
        SELECT gvkey, iid, "from"::date AS from_date, "thru"::date AS thru_date
        FROM comp.idxcst_his
        WHERE gvkeyx = '{SP500_GVKEYX}'
          AND ("thru" IS NULL OR "thru" >= '{start}'::date)
          AND "from" <= '{end}'::date
        """
    )
    members["from_date"] = pd.to_datetime(members["from_date"])
    members["thru_date"] = pd.to_datetime(members["thru_date"])
    members["thru_date"] = members["thru_date"].fillna(pd.Timestamp(end))
    gvkey_list = members["gvkey"].unique().tolist()
    gvkey_csv = ",".join(f"'{g}'" for g in gvkey_list)

    # Step 2: (gvkey, iid) → CUSIP-9 from Compustat security table.
    # comp.security has multiple iid rows per gvkey (one per share class — e.g.
    # AAPL has iid '01' = AAPL and iid '90C' = AAPL.). idxcst_his also reports
    # iid, so we match on both.
    sec = conn.raw_sql(
        f"""
        SELECT gvkey, iid, tic, cusip
        FROM comp.security
        WHERE gvkey IN ({gvkey_csv})
          AND cusip IS NOT NULL
          AND LENGTH(cusip) = 9
        """
    )
    sec["cusip8"] = sec["cusip"].str[:8]
    # Map (gvkey, iid) → cusip8
    gvkey_iid_to_cusip8 = {
        (r["gvkey"], r["iid"]): r["cusip8"] for _, r in sec.iterrows()
    }
    # Fallback: also keep gvkey-only mapping for the iid='01' primary class
    gvkey_to_cusip8 = {}
    for _, r in sec.iterrows():
        if r["iid"] == "01":
            gvkey_to_cusip8[r["gvkey"]] = r["cusip8"]
    # Last-resort: any cusip for a gvkey
    for _, r in sec.iterrows():
        gvkey_to_cusip8.setdefault(r["gvkey"], r["cusip8"])

    cusip8_list = sec["cusip8"].dropna().unique().tolist()
    cusip8_csv = ",".join(f"'{c}'" for c in cusip8_list)

    # Step 3: CUSIP-8 → permno via CRSP msenames (also gets ticker history)
    names = conn.raw_sql(
        f"""
        SELECT permno, ticker, ncusip,
               namedt::date AS namedt, nameendt::date AS nameendt
        FROM crsp.msenames
        WHERE ncusip IN ({cusip8_csv})
        """
    )
    names["namedt"] = pd.to_datetime(names["namedt"])
    names["nameendt"] = pd.to_datetime(names["nameendt"])
    cusip8_to_permnos = names.groupby("ncusip")["permno"].unique().to_dict()

    # Step 4: build (date, permno, ticker) at each quarter-end. Include a
    # snapshot one quarter BEFORE start so the orchestrator can initialize T0
    # holdings from the most recent prior membership snapshot.
    start_ts = pd.Timestamp(start)
    pre_start = (start_ts - pd.offsets.QuarterEnd(1)).normalize()
    quarter_ends = pd.DatetimeIndex(
        [pre_start] + list(pd.date_range(start, end, freq="QE"))
    )
    rows = []
    missing_cusip = 0
    missing_permno = 0
    for d in quarter_ends:
        active = members[
            (members["from_date"] <= d) & (members["thru_date"] >= d)
        ]
        for _, m in active.iterrows():
            # Try (gvkey, iid) match first, fall back to gvkey-only
            cusip8 = gvkey_iid_to_cusip8.get((m["gvkey"], m["iid"]))
            if not cusip8:
                cusip8 = gvkey_to_cusip8.get(m["gvkey"])
            if not cusip8:
                missing_cusip += 1
                continue
            permnos = cusip8_to_permnos.get(cusip8, [])
            if len(permnos) == 0:
                missing_permno += 1
                continue
            permno = int(permnos[0])
            tkr_rows = names[
                (names["permno"] == permno)
                & (names["namedt"] <= d)
                & (names["nameendt"] >= d)
            ]
            ticker = tkr_rows.iloc[0]["ticker"] if not tkr_rows.empty else ""
            rows.append({
                "date": d.normalize(),
                "permno": permno,
                "gvkey": m["gvkey"],
                "ticker": ticker,
            })
    if missing_cusip or missing_permno:
        print(f"  [constituents] missing CUSIP for {missing_cusip} gvkey-rebal pairs, "
              f"missing permno for {missing_permno} cusip8-rebal pairs")

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
