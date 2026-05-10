"""Inverse-weighted S&P 500 backtest orchestrator.

Pipeline:
  1. Constituents from fja05680/sp500
  2. Trading calendar + quarterly rebalance dates from SPY
  3. SEC EDGAR company-facts (point-in-time shares outstanding)
  4. yfinance prices (auto_adjust=True)
  5. Compute inverse-MC weights at each rebalance
  6. Day-by-day TR simulation
  7. Build report (REPORT.md + CSVs)

Run:
    python inverse_spx_backtest.py --start 2015-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from lib import benchmark, constituents, metrics, prices, report, shares, ticker_aliases
from lib import backtest as bt
from lib import weights as W


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--refresh-prices", action="store_true")
    ap.add_argument("--refresh-sec", action="store_true")
    ap.add_argument("--refresh-constituents", action="store_true")
    ap.add_argument("--no-fetch", action="store_true",
                    help="Use cache only; fail if anything is missing")
    ap.add_argument("--max-tickers", type=int, default=None,
                    help="Limit universe size for testing (None = all)")
    args = ap.parse_args()

    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Constituents ----
    _log("Fetching fja05680 constituent history...")
    history = constituents.fetch_constituents_history(refresh=args.refresh_constituents)
    _log(f"  {history['ticker'].nunique()} unique tickers across {history['date'].nunique()} snapshot dates")

    # ---- 2. Trading calendar + rebalance dates ----
    _log("Fetching SPY for trading calendar...")
    cal = prices.trading_calendar(args.start, args.end)
    _log(f"  {len(cal)} trading days from {cal[0].date()} to {cal[-1].date()}")

    quarterly_rebals = constituents.rebalance_dates(args.start, args.end, cal)
    # Prepend T0 (first trading day) for portfolio initialization
    t0 = cal[0]
    rebal_list = [t0] + [d for d in quarterly_rebals if d > t0]
    _log(f"  {len(rebal_list)} rebalance dates (T0 + {len(rebal_list)-1} quarter-ends)")

    # ---- 3. Build universe ----
    universe_set: set[str] = set()
    for d in rebal_list:
        for t in constituents.constituents_at(d, history):
            mapped = ticker_aliases.remap(t)
            if mapped:
                universe_set.add(mapped)
    universe = sorted(universe_set)
    if args.max_tickers:
        universe = universe[:args.max_tickers]
    _log(f"  Universe size: {len(universe)} tickers (post-alias-remap)")

    # ---- 4. Fetch SEC EDGAR shares facts ----
    _log("Fetching SEC EDGAR company-facts...")
    sec_facts: dict[str, dict | None] = {}
    n_ok, n_miss = 0, 0
    for i, tkr in enumerate(universe):
        if i % 50 == 0:
            _log(f"  SEC: {i}/{len(universe)} ({n_ok} ok, {n_miss} missing)")
        if args.no_fetch:
            cache = shares._cache_path(tkr)
            if cache.exists():
                import json as _json
                with cache.open("r") as f:
                    sec_facts[tkr] = _json.load(f)
                n_ok += 1
            else:
                sec_facts[tkr] = None
                n_miss += 1
            continue
        facts = shares.fetch_company_facts(tkr, refresh=args.refresh_sec)
        sec_facts[tkr] = facts
        if facts:
            n_ok += 1
        else:
            n_miss += 1
    _log(f"  SEC done: {n_ok} ok, {n_miss} missing")

    # ---- 5. Fetch prices ----
    _log("Fetching prices...")
    price_data: dict[str, pd.DataFrame | None] = {}
    n_ok, n_miss = 0, 0
    for i, tkr in enumerate(universe):
        if i % 50 == 0:
            _log(f"  prices: {i}/{len(universe)} ({n_ok} ok, {n_miss} missing)")
        if args.no_fetch:
            cache = prices._cache_path(tkr)
            if cache.exists():
                df = pd.read_parquet(cache)
                df.index = pd.to_datetime(df.index)
                price_data[tkr] = df
                if not df.empty:
                    n_ok += 1
                else:
                    price_data[tkr] = None
                    n_miss += 1
            else:
                price_data[tkr] = None
                n_miss += 1
            continue
        df = prices.fetch_prices(tkr, args.start, args.end, refresh=args.refresh_prices)
        price_data[tkr] = df
        if df is not None and not df.empty:
            n_ok += 1
        else:
            n_miss += 1
    _log(f"  prices done: {n_ok} ok, {n_miss} missing")

    # Always fetch SPY for benchmark
    spy_df = prices.fetch_prices("SPY", args.start, args.end)
    if spy_df is None:
        _log("ERROR: could not fetch SPY benchmark")
        return 1

    # ---- 6. Compute weights at each rebal ----
    _log("Computing inverse-MC weights at each rebalance...")
    overrides = shares.load_manual_overrides()
    failures: list[dict] = []
    weights_per_rebal: dict[pd.Timestamp, pd.DataFrame] = {}
    for d in rebal_list:
        members = constituents.constituents_at(d, history)
        # Remap aliases & filter to our universe
        mapped: list[str] = []
        for t in members:
            m = ticker_aliases.remap(t)
            if m is None:
                continue
            if args.max_tickers and m not in universe:
                continue
            mapped.append(m)
        # Dedup
        mapped = sorted(set(mapped))
        w = W.compute_weights(d, mapped, sec_facts, price_data, overrides, failures)
        if w.empty:
            _log(f"  WARNING: rebal {d.date()} produced empty weights")
        weights_per_rebal[d] = w
        if d == rebal_list[0] or d == rebal_list[-1] or rebal_list.index(d) % 10 == 0:
            _log(f"  rebal {d.date()}: {len(w)} holdings, top weight {w['weight'].max()*100:.2f}%" if not w.empty else f"  rebal {d.date()}: empty")

    # ---- 7. Run backtest ----
    _log("Running daily TR simulation...")
    daily = bt.run_backtest(rebal_list, weights_per_rebal, price_data, cal)
    _log(f"  end value: {daily['cumulative_value'].iloc[-1]:.4f} (started at 1.0)")

    daily_slipped = bt.apply_slippage(daily, weights_per_rebal, bps_round_trip=25.0)

    # ---- 8. Benchmark ----
    spy_daily = benchmark.spy_total_return(args.start, args.end)
    _log(f"  SPY end value: {spy_daily['cumulative_value'].iloc[-1]:.4f}")

    # ---- 9. Report ----
    _log("Building REPORT.md...")
    md = report.build_report(
        inverse_daily=daily,
        spy_daily=spy_daily,
        inverse_slipped=daily_slipped,
        weights_per_rebal=weights_per_rebal,
        failures=failures,
        start=args.start,
        end=args.end,
        out_dir=out_dir,
    )
    (out_dir / "REPORT.md").write_text(md, encoding="utf-8")
    _log(f"Wrote {out_dir/'REPORT.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
