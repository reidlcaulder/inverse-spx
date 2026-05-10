"""Inverse-weighted S&P 500 backtest, WRDS edition.

Replaces the EDGAR/yfinance/fja05680 data layer with CRSP + Compustat:
  - Compustat `idxcst_his` for point-in-time S&P 500 membership
  - CRSP `dsf` for daily prices, shares, returns (TR includes dividends)
  - CRSP `dsedelist` for explicit delisting return codes
  - CRSP SPY (permno 84398) for benchmark

This eliminates survivorship bias because CRSP keeps delisted tickers.

Run:
    python inverse_spx_backtest_wrds.py --start 2015-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from lib import metrics
from lib import report as edgar_report
from lib import wrds_backtest as bt
from lib import wrds_data as wd


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--username", default=None,
                    help="WRDS username (defaults to WRDS_USERNAME env var)")
    ap.add_argument("--refresh", action="store_true",
                    help="Refresh all WRDS query caches")
    args = ap.parse_args()

    out_dir = Path("out_wrds")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Connect ----
    _log("Connecting to WRDS...")
    conn = wd.get_connection(args.username)

    try:
        # ---- 2. Constituents ----
        _log("Fetching S&P 500 constituents (Compustat idxcst_his + CCM link)...")
        constituents = wd.fetch_sp500_constituents(
            conn, args.start, args.end, refresh=args.refresh
        )
        _log(f"  {len(constituents)} (date, permno) pairs across {constituents['date'].nunique()} quarter-ends")
        all_permnos = constituents["permno"].unique().tolist()
        _log(f"  {len(all_permnos)} unique permnos ever in S&P 500 over window")

        # ---- 3. Daily data ----
        _log("Fetching CRSP daily prices/shares/returns for full universe...")
        daily = wd.fetch_daily_data(conn, all_permnos, args.start, args.end, refresh=args.refresh)
        _log(f"  {len(daily):,} (permno, date) rows; {daily['date'].min().date()} to {daily['date'].max().date()}")

        # ---- 4. Delistings ----
        _log("Fetching delisting events from CRSP dsedelist...")
        delistings = wd.fetch_delistings(conn, all_permnos, args.start, args.end, refresh=args.refresh)
        _log(f"  {len(delistings)} delisting events; non-null dlret: {delistings['dlret'].notna().sum()}")
        # Show a sample of bankrupt-or-acquired names
        if not delistings.empty:
            wipeouts = delistings[delistings["dlret"] < -0.5]
            if not wipeouts.empty:
                _log(f"  Wipe-outs (dlret < -50%): {len(wipeouts)}")

        # ---- 5. SPY benchmark ----
        _log("Fetching SPY total return from CRSP...")
        spy = wd.fetch_spy_total_return(conn, args.start, args.end, refresh=args.refresh)
        _log(f"  SPY: {len(spy)} trading days")

    finally:
        conn.close()
        _log("WRDS connection closed.")

    # ---- 6. Apply delisting returns into the daily ret series ----
    _log("Applying delisting returns to daily total-return series...")
    daily = bt.apply_delisting_returns(daily, delistings)

    # ---- 7. Build trading calendar + rebalance dates ----
    trading_days = pd.DatetimeIndex(sorted(daily["date"].unique())).intersection(
        pd.DatetimeIndex(sorted(spy["date"].unique()))
    )
    _log(f"  {len(trading_days)} trading days in common universe")

    # Quarterly rebalance: last trading day of each calendar quarter
    rebal_quarterly = (
        trading_days.to_series().groupby(trading_days.to_period("Q")).max().tolist()
    )
    t0 = trading_days[0]
    rebal_dates = [t0] + [d for d in rebal_quarterly if d > t0]
    _log(f"  {len(rebal_dates)} rebalance dates (T0 + {len(rebal_dates)-1} quarter-ends)")

    # ---- 8. Compute weights at each rebalance ----
    _log("Computing inverse-MC weights at each rebalance...")
    failures: list[dict] = []
    weights_per_rebal: dict[pd.Timestamp, dict[int, float]] = {}

    for d in rebal_dates:
        # Find the Compustat-sanctioned membership at this date
        # (constituents was built at quarter-ends; find nearest snapshot ≤ d)
        snapshot_dates = sorted(constituents["date"].unique())
        snapshot_dates = [sd for sd in snapshot_dates if sd <= d]
        if not snapshot_dates:
            members_at_d = []
        else:
            members_at_d = constituents[
                constituents["date"] == snapshot_dates[-1]
            ]["permno"].tolist()

        w = bt.compute_inverse_weights(daily, d, members_at_d, failures)
        weights_per_rebal[d] = w
        if d == rebal_dates[0] or d == rebal_dates[-1] or rebal_dates.index(d) % 10 == 0:
            top_w = max(w.values()) * 100 if w else 0.0
            _log(f"  rebal {d.date()}: {len(w)} holdings, top weight {top_w:.2f}%")

    # ---- 9. Build returns matrix and run sim ----
    _log("Building returns matrix...")
    returns_matrix = bt.build_returns_matrix(daily, trading_days)
    _log(f"  matrix shape: {returns_matrix.shape}")

    _log("Running daily TR simulation...")
    daily_result = bt.run_backtest_returns(
        rebal_dates, weights_per_rebal, returns_matrix, trading_days
    )
    _log(f"  end value: {daily_result['cumulative_value'].iloc[-1]:.4f} (started at 1.0)")

    # ---- 10. Build SPY benchmark series with the same trading_days ----
    spy_indexed = spy.set_index("date").sort_index()
    spy_indexed = spy_indexed.reindex(trading_days)
    spy_indexed["ret"] = spy_indexed["ret"].fillna(0.0)
    spy_cum = (1 + spy_indexed["ret"]).cumprod()
    spy_cum.iloc[0] = 1.0
    spy_daily = pd.DataFrame({
        "cumulative_value": spy_cum,
        "daily_return": spy_indexed["ret"],
    })
    _log(f"  SPY end value: {spy_daily['cumulative_value'].iloc[-1]:.4f}")

    # ---- 11. Translate weights to a DataFrame shape the existing report expects ----
    weights_df_per_rebal: dict[pd.Timestamp, pd.DataFrame] = {}
    for d, w in weights_per_rebal.items():
        # Pull MC, price, ticker for each permno
        rows = []
        for permno, weight in w.items():
            row = daily[(daily["date"] == d) & (daily["permno"] == permno)]
            if row.empty:
                continue
            r = row.iloc[0]
            tk = constituents[
                (constituents["date"] <= d) & (constituents["permno"] == permno)
            ]
            ticker = tk.sort_values("date").iloc[-1]["ticker"] if not tk.empty else str(permno)
            rows.append({
                "ticker": ticker or str(permno),
                "shares": r["shares"],
                "price": r["price"],
                "mc": r["mc"],
                "inv_mc": 1.0 / r["mc"],
                "weight": weight,
                "source": "wrds",
            })
        df_d = pd.DataFrame(rows)
        if df_d.empty:
            df_d = pd.DataFrame(columns=["ticker", "shares", "price", "mc",
                                         "inv_mc", "weight", "source"])
        else:
            df_d = df_d.sort_values("weight", ascending=False)
        weights_df_per_rebal[d] = df_d

    # ---- 12. Slippage scenario ----
    from lib import backtest as legacy_bt
    daily_slipped = legacy_bt.apply_slippage(
        daily_result, weights_df_per_rebal, bps_round_trip=25.0
    )

    # ---- 13. Report ----
    _log("Building REPORT.md...")
    md = edgar_report.build_report(
        inverse_daily=daily_result,
        spy_daily=spy_daily,
        inverse_slipped=daily_slipped,
        weights_per_rebal=weights_df_per_rebal,
        failures=failures,
        start=args.start,
        end=args.end,
        out_dir=out_dir,
    )
    # Add a header noting this is the WRDS edition
    header = (
        "# Inverse-Weighted S&P 500 Backtest — **WRDS / CRSP edition**\n\n"
        "This run uses CRSP daily stock files and Compustat S&P 500 constituents — "
        "the gold-standard data sources, with proper delisting handling and no "
        "survivorship bias. Compare against the EDGAR/yfinance run at `out/REPORT.md`.\n\n"
        "---\n\n"
    )
    (out_dir / "REPORT.md").write_text(header + md, encoding="utf-8")
    _log(f"Wrote {out_dir/'REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
