"""SPY total-return benchmark."""

from __future__ import annotations

import pandas as pd

from . import prices as prices_mod


def spy_total_return(start: str, end: str, initial_value: float = 1.0) -> pd.DataFrame:
    """Returns DataFrame indexed by trading day with daily_return, cumulative_value."""
    df = prices_mod.fetch_prices("SPY", start, end)
    if df is None or df.empty:
        raise RuntimeError("Could not fetch SPY")
    closes = df["Close"].dropna()
    closes = closes / closes.iloc[0] * initial_value
    out = pd.DataFrame({
        "cumulative_value": closes,
        "daily_return": closes.pct_change().fillna(0.0),
    })
    return out
