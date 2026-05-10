"""Compare Inverse-SPX vs SPY, IWM (Russell 2000), RSP (S&P 500 Equal Weight),
IJR (S&P SmallCap 600), AVUV (small-cap value).

Uses our `out_full/cumulative.csv` for inverse-SPX, yfinance auto_adjust=True
total returns for the others. Writes:
  - docs/comparison.png            (cumulative growth, log-scale)
  - docs/comparison_stats.md       (table of CAGR / Sharpe / max DD per fund)
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import metrics  # noqa: E402

ALTERNATIVES = {
    "SPY":  ("SPY", "S&P 500 (cap-weight)",       "#7f7f7f"),
    "RSP":  ("RSP", "S&P 500 equal-weight",       "#2ca02c"),
    "IJR":  ("IJR", "S&P SmallCap 600",           "#d62728"),
    "IWM":  ("IWM", "Russell 2000",               "#ff7f0e"),
    "AVUV": ("AVUV", "Avantis US Small Cap Value", "#9467bd"),
}


def pull_total_return(ticker: str, start: str, end: str) -> pd.Series:
    df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
    if df is None or df.empty:
        return pd.Series(dtype=float, name=ticker)
    closes = df["Close"].copy()
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    return closes


def main():
    inv = pd.read_csv("out_full/cumulative.csv", index_col=0, parse_dates=True).sort_index()
    inv.index = inv.index.normalize()
    inverse_spx = inv["inverse_v"]
    start = inv.index[0].strftime("%Y-%m-%d")
    end = (inv.index[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    series_dict: dict[str, pd.Series] = {"Inverse-SPX": inverse_spx}
    for key, (tk, label, _color) in ALTERNATIVES.items():
        s = pull_total_return(tk, start, end)
        if s.empty:
            print(f"  {tk}: no data")
            continue
        # Normalize each series to start at $1 on its first available date
        # within the window
        s = s / s.iloc[0]
        series_dict[label] = s
        print(f"  {tk}: {len(s)} rows, {s.index[0].date()} to {s.index[-1].date()}, "
              f"end {s.iloc[-1]:.2f}x")

    # Build aligned DataFrame for plotting (each series can start on its own date)
    df = pd.concat(series_dict, axis=1)

    # ---- Chart ----
    fig, ax = plt.subplots(figsize=(11, 6))
    style_map = {
        "Inverse-SPX": ("#1f77b4", 1.8),
        ALTERNATIVES["SPY"][1]:  (ALTERNATIVES["SPY"][2],  1.4),
        ALTERNATIVES["RSP"][1]:  (ALTERNATIVES["RSP"][2],  1.4),
        ALTERNATIVES["IJR"][1]:  (ALTERNATIVES["IJR"][2],  1.4),
        ALTERNATIVES["IWM"][1]:  (ALTERNATIVES["IWM"][2],  1.4),
        ALTERNATIVES["AVUV"][1]: (ALTERNATIVES["AVUV"][2], 1.4),
    }
    for label in df.columns:
        col = df[label].dropna()
        color, lw = style_map.get(label, ("#000000", 1.2))
        ax.plot(col.index, col.values, label=f"{label}  ({col.iloc[-1]:.1f}x)",
                color=color, linewidth=lw)

    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}x"))
    ax.set_ylabel("Growth of $1 (log scale)")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.set_title("Inverse-SPX vs cap-weight, equal-weight, and small-cap alternatives",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", frameon=True, framealpha=0.95, fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.text(0.5, 0.01,
             "Each series starts at $1 on its first available date — alternatives launched at different times",
             ha="center", fontsize=8, color="#666")
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    out = Path("docs") / "comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")

    # ---- Stats table — for each alternative, compute stats over the OVERLAPPING window
    # with inverse-SPX so it's apples-to-apples ----
    rows = []
    for label, s in series_dict.items():
        if label == "Inverse-SPX":
            full = inverse_spx
            cum = full
            daily_ret = cum.pct_change().fillna(0.0)
        else:
            # Overlap with inverse-SPX index
            common = s.dropna().index.intersection(inverse_spx.index)
            if len(common) < 200:
                continue
            cum = s.loc[common]
            cum = cum / cum.iloc[0]
            daily_ret = cum.pct_change().fillna(0.0)
        cagr_v = metrics.cagr(cum)
        vol_v = metrics.annualized_vol(daily_ret)
        sh = metrics.sharpe(daily_ret)
        mdd = metrics.max_drawdown(cum)["mdd"]
        rows.append({
            "Series": label,
            "Window": f"{cum.index[0].date()} to {cum.index[-1].date()}",
            "Total return": cum.iloc[-1] / cum.iloc[0] - 1,
            "CAGR": cagr_v,
            "Vol": vol_v,
            "Sharpe": sh,
            "Max DD": mdd,
        })

    stats = pd.DataFrame(rows)

    md_lines = ["| Series | Window | Total return | CAGR | Vol | Sharpe | Max DD |",
                "|---|---|---:|---:|---:|---:|---:|"]
    for _, r in stats.iterrows():
        md_lines.append(
            f"| {r['Series']} | {r['Window']} | "
            f"{r['Total return']*100:+.1f}% | {r['CAGR']*100:+.2f}% | "
            f"{r['Vol']*100:.2f}% | {r['Sharpe']:.2f} | "
            f"{r['Max DD']*100:.2f}% |"
        )
    Path("docs/comparison_stats.md").write_text("\n".join(md_lines), encoding="utf-8")
    print("Wrote docs/comparison_stats.md")
    print()
    print("\n".join(md_lines))


if __name__ == "__main__":
    main()
