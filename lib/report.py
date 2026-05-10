"""REPORT.md generator."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from . import metrics as M


def _fmt_pct(x: float, digits: int = 2) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    return f"{x*100:+.{digits}f}%"


def _fmt_pct_abs(x: float, digits: int = 2) -> str:
    """Pct without leading +/- sign — for absolute weights, etc."""
    if x is None or pd.isna(x):
        return "n/a"
    return f"{x*100:.{digits}f}%"


def _fmt_num(x: float, digits: int = 2) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    return f"{x:.{digits}f}"


def _fmt_money(x: float) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    if abs(x) >= 1e12:
        return f"${x/1e12:.2f}T"
    if abs(x) >= 1e9:
        return f"${x/1e9:.2f}B"
    if abs(x) >= 1e6:
        return f"${x/1e6:.2f}M"
    return f"${x:,.0f}"


def _fmt_date(d) -> str:
    if d is None or pd.isna(d):
        return "n/a"
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def _headline_row(label: str, inverse_val: float, spy_val: float, fmt) -> str:
    return f"| {label} | {fmt(inverse_val)} | {fmt(spy_val)} | {fmt(inverse_val - spy_val) if not (pd.isna(inverse_val) or pd.isna(spy_val)) else 'n/a'} |"


def build_report(
    inverse_daily: pd.DataFrame,
    spy_daily: pd.DataFrame,
    inverse_slipped: pd.DataFrame,
    weights_per_rebal: dict[pd.Timestamp, pd.DataFrame],
    failures: list[dict],
    start: str,
    end: str,
    out_dir: Path,
) -> str:
    """Build REPORT.md content. Also writes companion CSVs into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Align on common index
    common_idx = inverse_daily.index.intersection(spy_daily.index)
    inv = inverse_daily.loc[common_idx]
    spy = spy_daily.loc[common_idx]
    slip = inverse_slipped.loc[common_idx]

    # Headline metrics
    inv_total = inv["cumulative_value"].iloc[-1] / inv["cumulative_value"].iloc[0] - 1
    spy_total = spy["cumulative_value"].iloc[-1] / spy["cumulative_value"].iloc[0] - 1
    inv_cagr = M.cagr(inv["cumulative_value"])
    spy_cagr = M.cagr(spy["cumulative_value"])
    inv_vol = M.annualized_vol(inv["daily_return"])
    spy_vol = M.annualized_vol(spy["daily_return"])
    inv_sh = M.sharpe(inv["daily_return"])
    spy_sh = M.sharpe(spy["daily_return"])
    inv_mdd = M.max_drawdown(inv["cumulative_value"])
    spy_mdd = M.max_drawdown(spy["cumulative_value"])

    slip_total = slip["cumulative_value"].iloc[-1] / slip["cumulative_value"].iloc[0] - 1
    slip_cagr = M.cagr(slip["cumulative_value"])

    # Yearly returns
    inv_yearly = M.calendar_year_returns(inv["cumulative_value"])
    spy_yearly = M.calendar_year_returns(spy["cumulative_value"])

    # Drawdowns
    top_dd = M.top_drawdowns(inv["cumulative_value"], n=5)

    # Turnover
    turn = M.turnover_table(weights_per_rebal)
    avg_turn = turn["turnover_oneway"].dropna().mean() if not turn.empty else float("nan")

    # Yearly cumulative snapshots
    yr_end_idx = pd.DatetimeIndex(
        [g.index[-1] for _, g in inv.groupby(inv.index.year)]
    )
    yearly_cum = pd.DataFrame({
        "year": [d.year for d in yr_end_idx],
        "inverse_value": [inv["cumulative_value"].loc[d] for d in yr_end_idx],
        "spy_value": [spy["cumulative_value"].loc[d] for d in yr_end_idx],
    })

    # Concentration: bottom-decile-by-MC share at each year-end's nearest rebal
    def share_in_bottom_decile_by_mc(w: pd.DataFrame) -> float:
        if w.empty:
            return float("nan")
        w_sorted = w.sort_values("mc")
        n_decile = max(1, len(w_sorted) // 10)
        return float(w_sorted.head(n_decile)["weight"].sum())

    rebal_dates_sorted = sorted(weights_per_rebal.keys())
    yr_concentration = []
    for y in sorted({d.year for d in rebal_dates_sorted}):
        yr_rebals = [d for d in rebal_dates_sorted if d.year == y]
        if not yr_rebals:
            continue
        last = yr_rebals[-1]
        w = weights_per_rebal[last]
        yr_concentration.append({
            "year": y,
            "rebal_date": last,
            "n_holdings": len(w),
            "top_weight_pct": w["weight"].max() if not w.empty else float("nan"),
            "top10_pct": w["weight"].nlargest(10).sum() if not w.empty else float("nan"),
            "bottom_decile_share": share_in_bottom_decile_by_mc(w),
        })

    # Failures summary
    fail_df = pd.DataFrame(failures) if failures else pd.DataFrame(columns=["date", "ticker", "reason"])
    fail_df.to_csv(out_dir / "failures.csv", index=False)
    reason_counts = Counter([f["reason"] for f in failures]) if failures else {}
    total_ticker_rebal_pairs = sum(len(w) for w in weights_per_rebal.values()) + len(fail_df)
    fail_pct = len(fail_df) / total_ticker_rebal_pairs * 100 if total_ticker_rebal_pairs > 0 else 0.0

    # Turnover CSV
    turn.to_csv(out_dir / "turnover.csv", index=False)
    # Daily returns + cumulative CSVs
    pd.DataFrame({
        "inverse_return": inv["daily_return"],
        "spy_return": spy["daily_return"],
    }).to_csv(out_dir / "daily_returns.csv")
    pd.DataFrame({
        "inverse_v": inv["cumulative_value"],
        "spy_v": spy["cumulative_value"],
        "inverse_v_with_25bps_slip": slip["cumulative_value"],
    }).to_csv(out_dir / "cumulative.csv")

    # Per-year top-20 holdings (smallest constituents = biggest weights)
    for y in sorted({d.year for d in rebal_dates_sorted}):
        yr_rebals = [d for d in rebal_dates_sorted if d.year == y]
        if not yr_rebals:
            continue
        w = weights_per_rebal[yr_rebals[-1]]
        top20 = w.nlargest(20, "weight")[["ticker", "weight", "mc", "shares", "price"]].copy()
        top20.to_csv(out_dir / f"holdings_top20_{y}.csv", index=False)

    # ---- Build markdown ----

    lines: list[str] = []
    lines.append(f"# Inverse-Weighted S&P 500 Backtest — {start} to {end}\n")
    lines.append(
        "**Methodology**\n"
        "- Universe: S&P 500 constituents at each rebalance date (point-in-time, fja05680/sp500)\n"
        "- Weighting: pure mathematical inverse of cap-weight, `w_i = (1/MC_i) / Σ(1/MC_j)`, no per-name cap\n"
        "- Rebalance: quarterly, last trading day of each calendar quarter (close-to-close, no look-ahead)\n"
        "- Returns: total return (yfinance `auto_adjust=True`)\n"
        "- Benchmark: SPY total return over the same window\n"
        "- Risk-free rate for Sharpe: 0% (Sharpe-equivalent — disclosed)\n"
    )

    lines.append("## Headline metrics\n")
    lines.append("| Metric | Inverse-SPX | SPY | Inverse − SPY |")
    lines.append("|---|---:|---:|---:|")
    lines.append(_headline_row("Total return", inv_total, spy_total, _fmt_pct))
    lines.append(_headline_row("CAGR", inv_cagr, spy_cagr, _fmt_pct))
    lines.append(_headline_row("Annualized volatility", inv_vol, spy_vol, _fmt_pct))
    lines.append(_headline_row("Sharpe (rf=0)", inv_sh, spy_sh, _fmt_num))
    lines.append(_headline_row("Max drawdown", inv_mdd["mdd"], spy_mdd["mdd"], _fmt_pct))
    lines.append("")
    lines.append(f"- Inverse-SPX max drawdown: {_fmt_pct(inv_mdd['mdd'])} ({_fmt_date(inv_mdd['peak_date'])} → {_fmt_date(inv_mdd['trough_date'])}, recovered {_fmt_date(inv_mdd['recovery_date'])})")
    lines.append(f"- SPY max drawdown: {_fmt_pct(spy_mdd['mdd'])} ({_fmt_date(spy_mdd['peak_date'])} → {_fmt_date(spy_mdd['trough_date'])}, recovered {_fmt_date(spy_mdd['recovery_date'])})")
    lines.append("")

    lines.append("### With 25 bps round-trip slippage applied per rebalance\n")
    lines.append("Real-world execution on a small-cap-tilted book is not free. This scenario applies a 25 bps round-trip slippage charge against the rebalanced fraction (turnover) at each rebalance.\n")
    lines.append("| Metric | Inverse-SPX (gross) | Inverse-SPX (slipped) | SPY |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Total return | {_fmt_pct(inv_total)} | {_fmt_pct(slip_total)} | {_fmt_pct(spy_total)} |")
    lines.append(f"| CAGR | {_fmt_pct(inv_cagr)} | {_fmt_pct(slip_cagr)} | {_fmt_pct(spy_cagr)} |")
    lines.append("")

    lines.append("## Calendar-year returns\n")
    lines.append("| Year | Inverse-SPX | SPY | Spread |")
    lines.append("|---|---:|---:|---:|")
    years = sorted(set(inv_yearly.index) | set(spy_yearly.index))
    for y in years:
        ir = inv_yearly.get(y, float("nan"))
        sr = spy_yearly.get(y, float("nan"))
        spread = ir - sr if not (pd.isna(ir) or pd.isna(sr)) else float("nan")
        lines.append(f"| {y} | {_fmt_pct(ir)} | {_fmt_pct(sr)} | {_fmt_pct(spread)} |")
    lines.append("")

    lines.append("## Cumulative growth of $1 (year-end)\n")
    lines.append("| Year-end | Inverse-SPX | SPY |")
    lines.append("|---|---:|---:|")
    for _, row in yearly_cum.iterrows():
        lines.append(f"| {int(row['year'])} | {_fmt_num(row['inverse_value'], 3)} | {_fmt_num(row['spy_value'], 3)} |")
    lines.append("")

    lines.append("## Top 5 drawdowns (Inverse-SPX)\n")
    lines.append("| Peak | Trough | Recovery | Depth | Days to recover |")
    lines.append("|---|---|---|---:|---:|")
    for dd in top_dd:
        rec = _fmt_date(dd["recovery_date"]) if dd["recovery_date"] else "ongoing"
        days = dd["days_to_recover"] if dd["days_to_recover"] is not None else "—"
        lines.append(
            f"| {_fmt_date(dd['peak_date'])} | {_fmt_date(dd['trough_date'])} | {rec} | {_fmt_pct(dd['depth'])} | {days} |"
        )
    lines.append("")

    lines.append("## Concentration profile (year-end weights)\n")
    lines.append("| Year | N holdings | Top weight | Top-10 weight | % in bottom decile by MC |")
    lines.append("|---|---:|---:|---:|---:|")
    for c in yr_concentration:
        lines.append(
            f"| {c['year']} | {c['n_holdings']} | {_fmt_pct_abs(c['top_weight_pct'])} | "
            f"{_fmt_pct_abs(c['top10_pct'])} | {_fmt_pct_abs(c['bottom_decile_share'])} |"
        )
    lines.append("")

    lines.append("## Turnover\n")
    lines.append(f"- Average one-way turnover per rebalance: {_fmt_pct_abs(avg_turn)}")
    lines.append(f"- Total rebalances: {len(turn)}")
    lines.append(f"- Annualized one-way turnover: {_fmt_pct_abs(avg_turn * 4)} (quarterly × 4)")
    lines.append("- Detail: see `out/turnover.csv`")
    lines.append("")

    lines.append("## Failures (tickers dropped at rebalance)\n")
    lines.append(f"- Total ticker-rebalance failures: {len(fail_df)} of {total_ticker_rebal_pairs} pairs ({fail_pct:.1f}%)")
    if reason_counts:
        lines.append("- By reason:")
        for reason, count in sorted(reason_counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - `{reason}`: {count}")
    lines.append("- Full list: see `out/failures.csv`")
    lines.append("")

    lines.append("## Limitations & caveats\n")
    lines.append(
        "1. **Survivorship bias.** Delisted small-caps that yfinance cannot price are dropped. Inverse-weighted strategies are *especially* sensitive: the smallest names get the largest weights, and the smallest names are also the most likely to delist (bankruptcy, acquisition, falling below S&P thresholds). This biases the backtest's return upward versus what an investor would actually have experienced. The number of dropped tickers per period is in `out/failures.csv`.\n"
        "2. **~45-90 day fundamentals lag.** SEC requires 10-Q within ~40 days of period end. The cover-page CSO at our 2024-09-30 rebalance is typically the value reported in the Q2 10-Q filed around 2024-07-25. This is realistic — it's the data an investor would actually have available — but means market caps lag actual share counts by up to one quarter.\n"
        "3. **Total CSO, not float-adjusted.** S&P 500 itself uses free-float market cap. We use total shares outstanding from XBRL filings. For names with concentrated insider holdings, this overstates MC and slightly under-weights them in the inverse scheme.\n"
        "4. **No transaction costs in headline numbers.** The slippage-adjusted scenario above applies a flat 25 bps round-trip charge against turnover. Actual execution costs on a small-cap-tilted book during stress periods could be materially higher.\n"
        "5. **No taxes.** Quarterly rebalancing of a turnover-heavy strategy in a taxable account would generate substantial short-term capital gains.\n"
        "6. **fja05680 is a community-maintained constituent list, not S&P-licensed.** Spot checks against known additions/deletions are reasonable, but treat exact membership as approximate.\n"
        "7. **yfinance occasional split mis-application.** Spot-check NVDA 10:1 (June 2024), AAPL 4:1 (Aug 2020), TSLA 3:1 (Aug 2022), AMZN 20:1 (June 2022), GOOGL 20:1 (July 2022).\n"
    )

    lines.append("## Reproducibility\n")
    lines.append("```")
    lines.append(f"python inverse_spx_backtest.py --start {start} --end {end}")
    lines.append("```")
    lines.append("Cache files under `data/cache/`. Companion CSVs in `out/`.")
    lines.append("")

    return "\n".join(lines)
