"""Render the cumulative-growth chart for the README.

Reads out_full/cumulative.csv and writes docs/cumulative.png and
docs/cumulative_log.png (log y-axis variant).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


def _format_axes(ax, log: bool):
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, which="major", alpha=0.3, linestyle="--")
    if log:
        ax.set_yscale("log")
        ax.set_ylabel("Growth of \\$1 (log scale)")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}x"))
    else:
        ax.set_ylabel("Growth of \\$1")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}x"))


def render(cum_path: Path, out_dir: Path) -> None:
    df = pd.read_csv(cum_path, index_col=0, parse_dates=True).sort_index()
    out_dir.mkdir(parents=True, exist_ok=True)

    inverse_color = "#1f77b4"
    spy_color = "#7f7f7f"

    final_inv = df["inverse_v"].iloc[-1]
    final_spy = df["spy_v"].iloc[-1]
    start_d = df.index[0].strftime("%Y-%m-%d")
    end_d = df.index[-1].strftime("%Y-%m-%d")

    for log_scale, suffix in [(True, "_log"), (False, "")]:
        fig, ax = plt.subplots(figsize=(11, 5.5))
        ax.plot(df.index, df["inverse_v"], label=f"Inverse-SPX  ({final_inv:.1f}x)",
                color=inverse_color, linewidth=1.6)
        ax.plot(df.index, df["spy_v"], label=f"SPY  ({final_spy:.1f}x)",
                color=spy_color, linewidth=1.6)

        ax.set_title(
            f"Inverse-Weighted S&P 500 vs SPY  —  {start_d} to {end_d}",
            fontsize=12, fontweight="bold",
        )
        _format_axes(ax, log=log_scale)
        ax.legend(loc="upper left", frameon=True, framealpha=0.95)
        ax.set_xlabel("")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Footer with source breakdown
        boundary_label = "WRDS/CRSP through 2024-12-31  |  EDGAR/yfinance for 2025"
        fig.text(0.5, 0.01, boundary_label, ha="center", fontsize=8, color="#666")

        plt.tight_layout(rect=(0, 0.03, 1, 1))
        out_file = out_dir / f"cumulative{suffix}.png"
        plt.savefig(out_file, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Wrote {out_file}")


if __name__ == "__main__":
    render(Path("out_full/cumulative.csv"), Path("docs"))
