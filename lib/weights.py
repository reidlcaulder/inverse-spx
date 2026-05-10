"""Inverse-market-cap weighting.

w_i = (1/MC_i) / sum(1/MC_j) over the kept tickers, where MC_i = shares_i * price_i.

No per-name cap. The smallest constituent will get a wildly outsized weight
relative to the largest — that's the strategy.
"""

from __future__ import annotations

import pandas as pd

from . import shares as shares_mod


def _price_on_or_before(prices_df: pd.DataFrame, asof: pd.Timestamp) -> float | None:
    """Last 'Close' on or before asof. None if nothing qualifies."""
    if prices_df is None or prices_df.empty:
        return None
    sub = prices_df.loc[prices_df.index <= asof]
    if sub.empty:
        return None
    px = float(sub.iloc[-1]["Close"])
    return px if px > 0 else None


def compute_weights(
    rebal_date: pd.Timestamp,
    constituents: list[str],
    sec_facts: dict[str, dict | None],
    prices: dict[str, pd.DataFrame | None],
    manual_overrides: pd.DataFrame,
    failures_log: list[dict] | None = None,
) -> pd.DataFrame:
    """Compute inverse-MC weights as of rebal_date.

    Parameters
    ----------
    rebal_date : the as-of date for shares + price lookup
    constituents : tickers to weight (post-alias-remap)
    sec_facts : {ticker: company-facts dict} from shares.fetch_company_facts
    prices : {ticker: OHLCV DataFrame} from prices.fetch_prices
    manual_overrides : DataFrame from shares.load_manual_overrides
    failures_log : optional mutable list to append failure records to

    Returns DataFrame with columns:
        ticker, shares, price, mc, inv_mc, weight, source
    where weight sums to 1.0 across kept tickers.
    """
    rows = []
    for tkr in constituents:
        # Manual override takes priority (intentional — it's curated data)
        shares = shares_mod.shares_from_override(manual_overrides, tkr, rebal_date)
        source = "manual" if shares is not None else None

        if shares is None:
            facts = sec_facts.get(tkr)
            shares = shares_mod.shares_outstanding_at(facts, rebal_date)
            source = "sec" if shares is not None else None

        price = _price_on_or_before(prices.get(tkr), rebal_date)

        if shares is None or shares <= 0:
            if failures_log is not None:
                failures_log.append({
                    "date": rebal_date, "ticker": tkr, "reason": "no_shares"
                })
            continue
        if price is None:
            if failures_log is not None:
                failures_log.append({
                    "date": rebal_date, "ticker": tkr, "reason": "no_price"
                })
            continue

        mc = shares * price
        rows.append({
            "ticker": tkr,
            "shares": shares,
            "price": price,
            "mc": mc,
            "inv_mc": 1.0 / mc,
            "source": source,
        })

    if not rows:
        return pd.DataFrame(columns=["ticker", "shares", "price", "mc", "inv_mc", "weight", "source"])

    df = pd.DataFrame(rows)
    df["weight"] = df["inv_mc"] / df["inv_mc"].sum()
    df = df.sort_values("weight", ascending=False).reset_index(drop=True)
    return df
