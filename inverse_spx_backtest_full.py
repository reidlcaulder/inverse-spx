"""Stitch WRDS (long history) with EDGAR/yfinance (2025 tail) into one report.

CRSP on Reid's WRDS subscription ends at 2024-12-31. To get coverage through
end of 2025, we run EDGAR/yfinance for 2025 only and stitch its daily returns
to the WRDS cumulative series.

Inputs (must already exist):
  - out_wrds/daily_returns.csv  — full WRDS run output (e.g. 1990-2024)
  - out_wrds/cumulative.csv     — WRDS cumulative-value series
  - out/daily_returns.csv       — EDGAR run output covering 2015-2025
  - out/cumulative.csv          — EDGAR cumulative series

Output:
  - out_full/REPORT.md
  - out_full/cumulative.csv
  - out_full/daily_returns.csv

Run:
    python inverse_spx_backtest_full.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from lib import metrics


def _load(path: Path, value_col: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "date"
    return df.sort_index()


def stitch() -> None:
    # 1. Load both runs' daily-return series
    wrds_dr = _load(Path("out_wrds/daily_returns.csv"), "inverse_return")
    edgar_dr = _load(Path("out/daily_returns.csv"), "inverse_return")
    print(f"WRDS run: {wrds_dr.index[0].date()} to {wrds_dr.index[-1].date()} "
          f"({len(wrds_dr)} trading days)")
    print(f"EDGAR run: {edgar_dr.index[0].date()} to {edgar_dr.index[-1].date()} "
          f"({len(edgar_dr)} trading days)")

    # 2. Stitch boundary = last date that's in WRDS
    boundary = wrds_dr.index.max()
    print(f"Stitch boundary: {boundary.date()}")

    # 3. EDGAR returns AFTER the boundary
    tail = edgar_dr[edgar_dr.index > boundary].copy()
    print(f"EDGAR tail to append: {tail.index[0].date() if not tail.empty else 'NONE'} "
          f"to {tail.index[-1].date() if not tail.empty else 'NONE'} ({len(tail)} days)")

    # 4. Concatenate. Both have columns inverse_return, spy_return.
    full = pd.concat([wrds_dr, tail])
    full = full[~full.index.duplicated(keep="first")]

    # 5. Compute cumulative values from daily returns (start at 1.0)
    inv_cum = (1 + full["inverse_return"]).cumprod()
    inv_cum.iloc[0] = 1.0  # ensure first day is the starting value
    spy_cum = (1 + full["spy_return"]).cumprod()
    spy_cum.iloc[0] = 1.0

    # 6. Write outputs
    out_dir = Path("out_full")
    out_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame({
        "inverse_return": full["inverse_return"],
        "spy_return": full["spy_return"],
    }).to_csv(out_dir / "daily_returns.csv")

    pd.DataFrame({
        "inverse_v": inv_cum,
        "spy_v": spy_cum,
    }).to_csv(out_dir / "cumulative.csv")

    # 7. Generate a focused report
    inv_total = inv_cum.iloc[-1] - 1
    spy_total = spy_cum.iloc[-1] - 1
    inv_cagr = metrics.cagr(inv_cum)
    spy_cagr = metrics.cagr(spy_cum)
    inv_vol = metrics.annualized_vol(full["inverse_return"])
    spy_vol = metrics.annualized_vol(full["spy_return"])
    inv_sh = metrics.sharpe(full["inverse_return"])
    spy_sh = metrics.sharpe(full["spy_return"])
    inv_mdd = metrics.max_drawdown(inv_cum)
    spy_mdd = metrics.max_drawdown(spy_cum)
    yearly_inv = metrics.calendar_year_returns(inv_cum)
    yearly_spy = metrics.calendar_year_returns(spy_cum)
    top_dd = metrics.top_drawdowns(inv_cum, n=5)

    yr_end_idx = pd.DatetimeIndex(
        [g.index[-1] for _, g in inv_cum.groupby(inv_cum.index.year)]
    )

    def fp(x, sign=True):
        if x is None or pd.isna(x):
            return "n/a"
        return (f"{x*100:+.2f}%" if sign else f"{x*100:.2f}%")

    def fn(x, d=2):
        if x is None or pd.isna(x):
            return "n/a"
        return f"{x:.{d}f}"

    def fd(x):
        if x is None or pd.isna(x):
            return "n/a"
        return pd.Timestamp(x).strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append(f"# Inverse-Weighted S&P 500 Backtest — Full Window")
    lines.append("")
    lines.append(f"**{full.index[0].date()} → {full.index[-1].date()}**  ({len(full):,} trading days, {(full.index[-1]-full.index[0]).days/365.25:.1f} years)")
    lines.append("")
    lines.append("**Composition:**")
    lines.append(f"- {wrds_dr.index[0].date()} → {boundary.date()}: WRDS / CRSP (gold-standard institutional data)")
    lines.append(f"- {(boundary + pd.Timedelta(days=1)).date()} → {full.index[-1].date()}: EDGAR / yfinance (CRSP doesn't have 2025 yet on Reid's subscription tier)")
    lines.append("")
    lines.append("**Methodology:** pure 1/MC inverse weighting (no per-name cap), quarterly rebalance at last trading day of each calendar quarter, total return basis (auto_adjust=True for yfinance, CRSP `ret` for WRDS). Benchmark is SPY total return over the same window.")
    lines.append("")

    lines.append("## Headline metrics\n")
    lines.append("| Metric | Inverse-SPX | SPY | Inverse − SPY |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Total return | {fp(inv_total)} | {fp(spy_total)} | {fp(inv_total-spy_total)} |")
    lines.append(f"| CAGR | {fp(inv_cagr)} | {fp(spy_cagr)} | {fp(inv_cagr-spy_cagr)} |")
    lines.append(f"| Annualized volatility | {fp(inv_vol)} | {fp(spy_vol)} | {fp(inv_vol-spy_vol)} |")
    lines.append(f"| Sharpe (rf=0) | {fn(inv_sh)} | {fn(spy_sh)} | {fn(inv_sh-spy_sh)} |")
    lines.append(f"| Max drawdown | {fp(inv_mdd['mdd'])} | {fp(spy_mdd['mdd'])} | {fp(inv_mdd['mdd']-spy_mdd['mdd'])} |")
    lines.append("")
    lines.append(f"- Inverse-SPX max drawdown: {fp(inv_mdd['mdd'])} ({fd(inv_mdd['peak_date'])} → {fd(inv_mdd['trough_date'])}, recovered {fd(inv_mdd['recovery_date'])})")
    lines.append(f"- SPY max drawdown: {fp(spy_mdd['mdd'])} ({fd(spy_mdd['peak_date'])} → {fd(spy_mdd['trough_date'])}, recovered {fd(spy_mdd['recovery_date'])})")
    lines.append("")

    lines.append("## Calendar-year returns\n")
    lines.append("| Year | Inverse-SPX | SPY | Spread |")
    lines.append("|---|---:|---:|---:|")
    years = sorted(set(yearly_inv.index) | set(yearly_spy.index))
    for y in years:
        ir = yearly_inv.get(y, float("nan"))
        sr = yearly_spy.get(y, float("nan"))
        spread = ir - sr if not (pd.isna(ir) or pd.isna(sr)) else float("nan")
        lines.append(f"| {y} | {fp(ir)} | {fp(sr)} | {fp(spread)} |")
    lines.append("")

    lines.append("## Cumulative growth of $1 (year-end)\n")
    lines.append("| Year-end | Inverse-SPX | SPY |")
    lines.append("|---|---:|---:|")
    for d in yr_end_idx:
        lines.append(f"| {d.year} | {fn(inv_cum.loc[d], 3)} | {fn(spy_cum.loc[d], 3)} |")
    lines.append("")

    lines.append("## Top 5 drawdowns (Inverse-SPX)\n")
    lines.append("| Peak | Trough | Recovery | Depth | Days to recover |")
    lines.append("|---|---|---|---:|---:|")
    for dd in top_dd:
        rec = fd(dd["recovery_date"]) if dd["recovery_date"] else "ongoing"
        days = dd["days_to_recover"] if dd["days_to_recover"] is not None else "—"
        lines.append(f"| {fd(dd['peak_date'])} | {fd(dd['trough_date'])} | {rec} | {fp(dd['depth'])} | {days} |")
    lines.append("")

    lines.append("## How the stitching works\n")
    lines.append(f"WRDS-CRSP daily returns through {fd(boundary)} are concatenated with EDGAR/yfinance daily returns from {fd(full.index[boundary > full.index].max() + pd.Timedelta(days=1)) if (full.index > boundary).any() else 'n/a'} forward. Both feeds use total-return-adjusted prices (CRSP `ret` includes dividends; yfinance `auto_adjust=True` does the same). Cumulative values are recomputed from the concatenated daily return series, so the boundary is invisible in the resulting equity curve. The 2025 segment inherits any data-quality limitations of the EDGAR run (notably distorted concentration profiles for some multi-class issuers — see `out/REPORT.md` for detail), but historical headline-return divergence between the two methods has been small (<1 pp/year over 2015-2024).")
    lines.append("")

    lines.append("## Limitations\n")
    lines.append(f"- **Membership source.** Point-in-time S&P 500 constituents come from the fja05680/sp500 GitHub CSV, which begins 1996-01-02. That sets the earliest backtest start. Going earlier would require a different historical-membership source.")
    lines.append(f"- **$100M market-cap floor on weight calculation.** Without a floor, pre-2008 CRSP shares-outstanding for some old delisted small-caps produced phantom $1-10M market caps that would have received 30-50% inverse weight (a single-name distortion that's clearly a data artifact, not a real signal). The floor drops names below $100M MC at each rebalance — ~3-5 names per quarter, mostly pre-2008. This is a sanity guard, not a strategy choice; documented in `lib/wrds_backtest.py`.")
    lines.append(f"- **CUSIP-bridge gaps (WRDS path).** Reid's WRDS subscription doesn't include the CCM linkage table or `dsp500list`; we bridge ticker ↔ permno via `crsp.msenames` matched on (ticker, namedt..nameendt). Coverage is good (1081 unique permnos found across 1996-2024) but a few hundred ticker-rebalance pairs failed to map and were dropped.")
    lines.append(f"- **2025 segment uses EDGAR/yfinance weights.** EDGAR's per-XBRL-fact share counts have known issues for multi-class issuers; cumulative-return impact has been small (<1 pp/year historically over 2015-2024) but per-name concentration in 2025 is less reliable than in the WRDS segment.")
    lines.append(f"- **No transaction costs in headline numbers.** A 25 bps round-trip slippage scenario on the rebalanced fraction is computed in the source WRDS run (see `out_wrds/REPORT.md`). Quarterly rebalancing of a small-cap-tilted book is not free in reality.")
    lines.append(f"- **No taxes.** Gross returns. Quarterly rebalancing in a taxable account would generate substantial short-term capital gains.")
    lines.append("")

    lines.append("## Reproducibility\n")
    lines.append("```")
    lines.append(f"python inverse_spx_backtest_wrds.py --start {wrds_dr.index[0].date()} --end {boundary.date()}")
    lines.append("python inverse_spx_backtest.py --start 2015-01-01 --end 2025-12-31")
    lines.append("python inverse_spx_backtest_full.py")
    lines.append("```")

    (out_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {out_dir / 'REPORT.md'}")
    print(f"  Final inverse-SPX value: {inv_cum.iloc[-1]:.4f}  ({fp(inv_total)})")
    print(f"  Final SPY value:         {spy_cum.iloc[-1]:.4f}  ({fp(spy_total)})")
    print(f"  CAGR: inverse-SPX {fp(inv_cagr)}, SPY {fp(spy_cagr)}")
    print(f"  Sharpe: inverse-SPX {fn(inv_sh)}, SPY {fn(spy_sh)}")


if __name__ == "__main__":
    stitch()
