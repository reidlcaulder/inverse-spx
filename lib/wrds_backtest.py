"""Returns-based backtest simulator for the WRDS data path.

Uses CRSP `ret` (total return) directly rather than reconstructing returns from
prices. This simplifies the simulator AND naturally handles dividends, splits,
and delisting returns once they're folded into the returns time-series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def apply_delisting_returns(
    daily: pd.DataFrame, delistings: pd.DataFrame
) -> pd.DataFrame:
    """Augment daily['ret'] with delisting returns on dlstdt.

    For each permno that delists, compound `dlret` into the LAST available
    trading-day return for that permno on or before `dlstdt`.

    Vectorized for ~5M-row daily frames: pre-computes per-permno last-date
    on or before each delisting date in one groupby pass rather than O(N)
    filtering per delisting.
    """
    # Filter to delistings with a usable dlret
    dl = delistings.copy()
    dl = dl[dl["dlret"].notna()]
    if dl.empty:
        return daily

    # For each permno, pre-compute its set of trading dates as a sorted Series
    out = daily.copy().reset_index(drop=True)
    # Multi-index lookup is O(log n); set once
    indexed = out.set_index(["permno", "date"])["ret"]

    # Group daily by permno once to find available trading dates per permno
    permno_to_dates: dict = {}
    for permno, g in out.groupby("permno"):
        permno_to_dates[permno] = g["date"].sort_values().values  # numpy datetime64

    import numpy as np

    updates = []  # list of (permno, last_date, new_ret) tuples
    for _, row in dl.iterrows():
        permno = row["permno"]
        dlstdt = pd.Timestamp(row["dlstdt"]).to_datetime64()
        dlret = float(row["dlret"])
        dates = permno_to_dates.get(permno)
        if dates is None or len(dates) == 0:
            continue
        # Last available date on or before dlstdt — binary search
        idx = np.searchsorted(dates, dlstdt, side="right") - 1
        if idx < 0:
            # Whole permno series is after dlstdt — fall back to first available
            last_date = dates[0]
        else:
            last_date = dates[idx]
        try:
            existing = indexed.loc[(permno, pd.Timestamp(last_date))]
        except KeyError:
            continue
        if pd.isna(existing):
            existing = 0.0
        new_ret = (1 + existing) * (1 + dlret) - 1
        updates.append((permno, pd.Timestamp(last_date), new_ret))

    if not updates:
        return daily

    upd_df = pd.DataFrame(updates, columns=["permno", "date", "_new_ret"])
    out = out.merge(upd_df, on=["permno", "date"], how="left")
    out["ret"] = out["_new_ret"].combine_first(out["ret"])
    out = out.drop(columns=["_new_ret"])
    return out


def build_returns_matrix(daily: pd.DataFrame, trading_days: pd.DatetimeIndex) -> pd.DataFrame:
    """Wide DataFrame: index=trading_days, columns=permno, values=ret (total return).

    Missing values become 0.0 (the position contributes nothing on days it
    doesn't trade — a halted or pre-IPO stock).
    """
    pivot = daily.pivot_table(
        index="date", columns="permno", values="ret", aggfunc="last"
    )
    pivot = pivot.reindex(trading_days).fillna(0.0)
    return pivot


def compute_inverse_weights(
    daily: pd.DataFrame,
    rebal_date: pd.Timestamp,
    constituent_permnos: list[int],
    failures_log: list[dict] | None = None,
    mc_floor: float = 100_000_000.0,
) -> dict[int, float]:
    """Pure 1/MC weighting at rebal_date for the given S&P 500 constituents.

    `mc_floor` (default $100M) drops names with computed market cap below that
    threshold — these are typically data-quality artifacts (stale CRSP
    shares-outstanding for delisted small-caps that crashed before their last
    trade), not real S&P 500 constituents. Without this floor, the inverse
    weighting blows up: a phantom $5M MC permno gets ~50% weight in a 1/MC scheme.

    Set mc_floor=0 to disable.

    Returns dict {permno: weight} summing to 1.0 across kept names.
    """
    rebal_data = daily[
        (daily["date"] == rebal_date) & daily["permno"].isin(constituent_permnos)
    ].copy()
    rebal_data = rebal_data[(rebal_data["mc"] > 0) & rebal_data["mc"].notna()]
    if mc_floor > 0:
        below_floor = rebal_data[rebal_data["mc"] < mc_floor]
        if failures_log is not None and not below_floor.empty:
            for _, r in below_floor.iterrows():
                failures_log.append({
                    "date": rebal_date, "permno": int(r["permno"]),
                    "reason": f"mc_below_floor_{int(mc_floor):d}"
                })
        rebal_data = rebal_data[rebal_data["mc"] >= mc_floor]
    if rebal_data.empty:
        return {}

    # Log failures (constituents we couldn't price on rebal_date)
    if failures_log is not None:
        kept = set(rebal_data["permno"])
        for p in constituent_permnos:
            if p not in kept:
                failures_log.append({
                    "date": rebal_date, "permno": p, "reason": "no_mc_at_rebal"
                })

    rebal_data["inv_mc"] = 1.0 / rebal_data["mc"]
    total_inv = rebal_data["inv_mc"].sum()
    return {
        int(row["permno"]): float(row["inv_mc"]) / total_inv
        for _, row in rebal_data.iterrows()
    }


def run_backtest_returns(
    rebal_dates: list[pd.Timestamp],
    weights_per_rebal: dict[pd.Timestamp, dict[int, float]],
    returns_matrix: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
    initial_value: float = 1.0,
) -> pd.DataFrame:
    """Daily-marked, weight-drift-aware total return simulator.

    Logic:
      - At T0 (first rebal_dates[0]): set weights = weights_per_rebal[T0].
      - Each subsequent day d:
          port_ret_d = Σ_i w_i * ret_i_d
          v_d = v_{d-1} * (1 + port_ret_d)
          weights drift: w_i_new = w_i * (1 + ret_i_d) / (1 + port_ret_d)
      - On rebalance days: AFTER recording d's return, snap weights to
        weights_per_rebal[d].
    """
    rebal_set = {pd.Timestamp(d).normalize() for d in rebal_dates}
    rebal_dates_sorted = sorted(rebal_set)
    t0 = rebal_dates_sorted[0]

    weights: dict[int, float] = dict(weights_per_rebal[t0])
    v = initial_value

    records = [{
        "date": t0,
        "daily_return": 0.0,
        "cumulative_value": v,
        "n_holdings": len(weights),
    }]

    after_t0 = trading_days[trading_days > t0]
    for d in after_t0:
        if d not in returns_matrix.index:
            records.append({
                "date": d, "daily_return": 0.0, "cumulative_value": v,
                "n_holdings": len(weights),
            })
            continue
        rets_today = returns_matrix.loc[d]
        # Portfolio return today
        port_ret = 0.0
        for p, w in weights.items():
            r = rets_today.get(p, 0.0)
            if pd.isna(r):
                r = 0.0
            port_ret += w * r

        # Weight drift
        if abs(1 + port_ret) > 1e-12:
            new_weights: dict[int, float] = {}
            for p, w in weights.items():
                r = rets_today.get(p, 0.0)
                if pd.isna(r):
                    r = 0.0
                new_w = w * (1 + r) / (1 + port_ret)
                if new_w > 0:
                    new_weights[p] = new_w
            weights = new_weights

        v *= (1 + port_ret)

        # Rebalance at close of d if it's a rebal date
        if d in rebal_set and d != trading_days[-1]:
            new_w = weights_per_rebal.get(d)
            if new_w:
                weights = dict(new_w)

        records.append({
            "date": d,
            "daily_return": port_ret,
            "cumulative_value": v,
            "n_holdings": len(weights),
        })

    return pd.DataFrame(records).set_index("date")
