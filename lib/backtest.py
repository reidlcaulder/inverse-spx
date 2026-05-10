"""Daily total-return portfolio simulator with quarterly rebalancing.

No look-ahead: at rebalance day d, weights are set using close prices on d, and
the first daily return contribution from the new holdings is on d+1.

Mid-quarter delisting handling: if a ticker has no trading on day d, we use its
last available close (forward-fill). This freezes the position at last value
until the next rebalance drops it. Conservative for cash-takeouts (we'd miss
the takeover premium); slightly favourable for wipe-outs that yfinance silently
truncates without a final-zero print.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _price_matrix(
    tickers: list[str],
    prices: dict[str, pd.DataFrame | None],
    trading_days: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Build a wide price DataFrame: index=trading_days, columns=tickers, values=Close.

    Missing dates are forward-filled (delisted/halted holdings stay at last close).
    """
    cols = {}
    for t in tickers:
        df = prices.get(t)
        if df is None or df.empty:
            cols[t] = pd.Series(np.nan, index=trading_days)
        else:
            s = df["Close"].reindex(trading_days).ffill()
            cols[t] = s
    return pd.DataFrame(cols, index=trading_days)


def run_backtest(
    rebal_dates: list[pd.Timestamp],
    weights_per_rebal: dict[pd.Timestamp, pd.DataFrame],
    prices: dict[str, pd.DataFrame | None],
    trading_days: pd.DatetimeIndex,
    initial_value: float = 1.0,
) -> pd.DataFrame:
    """Simulate the portfolio day-by-day.

    The first entry of `rebal_dates` is the T0 initialization date (typically
    the first trading day of the window). Subsequent entries are quarterly
    rebalance dates. Each must have a corresponding entry in weights_per_rebal.

    Returns DataFrame indexed by trading day with columns:
        daily_return, cumulative_value, n_holdings, gross_exposure
    """
    if not rebal_dates:
        raise ValueError("rebal_dates is empty")

    # Universe across all rebals
    universe: set[str] = set()
    for w in weights_per_rebal.values():
        universe.update(w["ticker"].tolist())
    if not universe:
        raise ValueError("No tickers in any weights snapshot")

    universe_list = sorted(universe)
    px = _price_matrix(universe_list, prices, trading_days)

    rebal_set = {pd.Timestamp(d).normalize() for d in rebal_dates}
    rebal_dates_sorted = sorted(rebal_set)
    t0 = rebal_dates_sorted[0]
    if t0 not in trading_days:
        raise ValueError(f"T0 rebal date {t0} is not in trading days")

    # Holdings as a Series indexed by ticker (shares per name; missing = 0)
    holdings = pd.Series(0.0, index=universe_list)

    # Initialize at T0: set holdings using close on T0 with `initial_value` AUM
    w0 = weights_per_rebal[t0]
    px_t0 = px.loc[t0]
    for _, row in w0.iterrows():
        tkr = row["ticker"]
        p = px_t0.get(tkr, np.nan)
        if pd.isna(p) or p <= 0:
            continue
        holdings[tkr] = (initial_value * row["weight"]) / p
    v_prev = initial_value

    records = []
    # Record T0 row (no return prior to start)
    records.append({
        "date": t0,
        "daily_return": 0.0,
        "cumulative_value": v_prev,
        "n_holdings": int((holdings != 0).sum()),
        "gross_exposure": float((holdings * px_t0).sum(skipna=True)),
    })

    after_t0 = trading_days[trading_days > t0]
    for d in after_t0:
        prices_today = px.loc[d]
        # mark to market using yesterday's holdings
        v_today = float((holdings * prices_today).sum(skipna=True))
        if v_prev <= 0 or not np.isfinite(v_today):
            daily_ret = 0.0
            v_today = max(v_today, 0.0)
        else:
            daily_ret = (v_today / v_prev) - 1.0

        # Rebalance at close if d is a rebal date
        if d in rebal_set and d != trading_days[-1]:
            w = weights_per_rebal.get(d)
            if w is not None and not w.empty:
                new_holdings = pd.Series(0.0, index=universe_list)
                for _, row in w.iterrows():
                    tkr = row["ticker"]
                    p = prices_today.get(tkr, np.nan)
                    if pd.isna(p) or p <= 0:
                        continue
                    new_holdings[tkr] = (v_today * row["weight"]) / p
                holdings = new_holdings

        records.append({
            "date": d,
            "daily_return": daily_ret,
            "cumulative_value": v_today,
            "n_holdings": int((holdings != 0).sum()),
            "gross_exposure": float((holdings * prices_today).sum(skipna=True)),
        })
        v_prev = v_today

    return pd.DataFrame(records).set_index("date")


def apply_slippage(
    daily: pd.DataFrame,
    weights_per_rebal: dict[pd.Timestamp, pd.DataFrame],
    bps_round_trip: float = 25.0,
) -> pd.DataFrame:
    """Apply a slippage drag at each rebalance based on one-way turnover.

    Subtracts (one_way_turnover * bps_round_trip / 10000) from cumulative value
    on each rebalance date. Rough but transparent — reflects the cost of
    rebalancing a small-cap-tilted book.

    Returns a copy of `daily` with adjusted cumulative_value and daily_return.
    """
    out = daily.copy()
    rebal_dates = sorted(weights_per_rebal.keys())
    # Compute one-way turnover at each rebal: 0.5 * sum(|w_new - w_old|)
    turn_by_date: dict[pd.Timestamp, float] = {}
    prev_w: pd.Series | None = None
    for d in rebal_dates:
        w = weights_per_rebal[d].set_index("ticker")["weight"]
        if prev_w is None:
            turn_by_date[d] = 0.0
        else:
            all_t = w.index.union(prev_w.index)
            wn = w.reindex(all_t).fillna(0.0)
            wo = prev_w.reindex(all_t).fillna(0.0)
            turn_by_date[d] = 0.5 * float((wn - wo).abs().sum())
        prev_w = w

    rate = bps_round_trip / 10000.0
    cum = out["cumulative_value"].copy()
    for d, t in turn_by_date.items():
        if d not in cum.index:
            continue
        # apply drag: position-rebalancing-fraction * round-trip-rate
        drag = t * rate
        cum.loc[d:] *= (1 - drag)
    out["cumulative_value"] = cum
    out["daily_return"] = cum.pct_change().fillna(0.0)
    return out
