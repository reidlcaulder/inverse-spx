"""Performance metrics: CAGR, vol, Sharpe, max drawdown, turnover."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def cagr(cum: pd.Series) -> float:
    """Compound annual growth rate from a cumulative-value series."""
    cum = cum.dropna()
    if len(cum) < 2:
        return 0.0
    total = cum.iloc[-1] / cum.iloc[0]
    n_days = (cum.index[-1] - cum.index[0]).days
    if n_days <= 0:
        return 0.0
    years = n_days / 365.25
    return float(total ** (1 / years) - 1)


def annualized_vol(daily_returns: pd.Series) -> float:
    r = daily_returns.dropna()
    if r.empty:
        return 0.0
    return float(r.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe(daily_returns: pd.Series, rf_annual: float = 0.0) -> float:
    """Annualized Sharpe ratio. rf_annual is annualized risk-free rate (default 0)."""
    r = daily_returns.dropna()
    if r.empty:
        return 0.0
    daily_rf = rf_annual / TRADING_DAYS_PER_YEAR
    excess = r - daily_rf
    if excess.std(ddof=1) == 0:
        return 0.0
    return float(excess.mean() / excess.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(cum: pd.Series) -> dict:
    """Returns dict with mdd (negative pct), peak_date, trough_date, recovery_date, recovery_days."""
    cum = cum.dropna()
    if cum.empty:
        return {"mdd": 0.0, "peak_date": None, "trough_date": None,
                "recovery_date": None, "recovery_days": None}
    running_max = cum.cummax()
    dd = cum / running_max - 1.0
    trough_date = dd.idxmin()
    mdd = float(dd.loc[trough_date])
    peak_date = cum.loc[:trough_date].idxmax()
    # First date after trough where cum recovers to peak value
    recovered = cum.loc[trough_date:][cum.loc[trough_date:] >= cum.loc[peak_date]]
    recovery_date = recovered.index[0] if not recovered.empty else None
    recovery_days = (recovery_date - trough_date).days if recovery_date is not None else None
    return {
        "mdd": mdd,
        "peak_date": peak_date,
        "trough_date": trough_date,
        "recovery_date": recovery_date,
        "recovery_days": recovery_days,
    }


def top_drawdowns(cum: pd.Series, n: int = 5) -> list[dict]:
    """Return the top-N drawdowns by depth. Each entry has peak/trough/recovery/depth/days_to_recover."""
    cum = cum.dropna()
    if cum.empty:
        return []
    running_max = cum.cummax()
    dd = cum / running_max - 1.0

    # Identify drawdown episodes: state machine.
    episodes: list[dict] = []
    in_dd = False
    peak_v = cum.iloc[0]
    peak_d = cum.index[0]
    trough_v = peak_v
    trough_d = peak_d
    for d, v in cum.items():
        if not in_dd:
            if v < peak_v:
                in_dd = True
                trough_v = v
                trough_d = d
        else:
            if v < trough_v:
                trough_v = v
                trough_d = d
            if v >= peak_v:
                episodes.append({
                    "peak_date": peak_d, "peak_value": peak_v,
                    "trough_date": trough_d, "trough_value": trough_v,
                    "recovery_date": d,
                    "depth": trough_v / peak_v - 1.0,
                    "days_to_recover": (d - trough_d).days,
                })
                in_dd = False
                peak_v = v
                peak_d = d
        if v > peak_v and not in_dd:
            peak_v = v
            peak_d = d
    if in_dd:
        episodes.append({
            "peak_date": peak_d, "peak_value": peak_v,
            "trough_date": trough_d, "trough_value": trough_v,
            "recovery_date": None,
            "depth": trough_v / peak_v - 1.0,
            "days_to_recover": None,
        })

    episodes.sort(key=lambda e: e["depth"])
    return episodes[:n]


def calendar_year_returns(cum: pd.Series) -> pd.Series:
    """Total return per calendar year. Year-end / prior year-end - 1."""
    cum = cum.dropna()
    if cum.empty:
        return pd.Series(dtype=float)
    yr_end = cum.groupby(cum.index.year).last()
    # First-year start uses beginning-of-series value
    first_year = yr_end.index[0]
    initial = cum.iloc[0]
    rets: dict[int, float] = {}
    prev = initial
    for y, v in yr_end.items():
        rets[int(y)] = v / prev - 1.0
        prev = v
    return pd.Series(rets)


def turnover_table(weights_per_rebal: dict[pd.Timestamp, pd.DataFrame]) -> pd.DataFrame:
    """One-way turnover at each rebalance: 0.5 * sum(|w_new - w_old|).

    Returns DataFrame with columns rebal_date, turnover_oneway, n_added, n_removed.
    """
    rows = []
    rebal_dates = sorted(weights_per_rebal.keys())
    prev_w: pd.Series | None = None
    prev_set: set[str] = set()
    for d in rebal_dates:
        w = weights_per_rebal[d].set_index("ticker")["weight"]
        cur_set = set(w.index)
        if prev_w is None:
            turn = float("nan")
            added = len(cur_set)
            removed = 0
        else:
            all_t = w.index.union(prev_w.index)
            wn = w.reindex(all_t).fillna(0.0)
            wo = prev_w.reindex(all_t).fillna(0.0)
            turn = 0.5 * float((wn - wo).abs().sum())
            added = len(cur_set - prev_set)
            removed = len(prev_set - cur_set)
        rows.append({"rebal_date": d, "turnover_oneway": turn,
                     "n_added": added, "n_removed": removed})
        prev_w = w
        prev_set = cur_set
    return pd.DataFrame(rows)
