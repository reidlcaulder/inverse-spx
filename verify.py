"""Quick end-to-end verification with AAPL.

Tests:
  1. fja05680 constituents fetch and date lookup
  2. yfinance price fetch (AAPL TR Jan 2015 -> Dec 2025)
  3. SEC EDGAR shares fetch (AAPL CSO at 2024-12-31)
  4. Weight calc on a single date (smoke test, 5-ticker mini-universe)
  5. Trading calendar
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from lib import constituents, prices, shares
from lib import weights as W


def main() -> int:
    Path("data/cache").mkdir(parents=True, exist_ok=True)

    # 1. Constituents
    print("\n[1] Fetching fja05680 constituent history...")
    history = constituents.fetch_constituents_history()
    print(f"    Got {len(history)} (date, ticker) rows; {history['ticker'].nunique()} unique tickers")
    print(f"    Date range: {history['date'].min().date()} to {history['date'].max().date()}")
    members_2015_q1 = constituents.constituents_at(pd.Timestamp("2015-03-31"), history)
    members_2024_q4 = constituents.constituents_at(pd.Timestamp("2024-12-31"), history)
    print(f"    2015-03-31 membership: {len(members_2015_q1)} tickers, e.g. {members_2015_q1[:5]}")
    print(f"    2024-12-31 membership: {len(members_2024_q4)} tickers, e.g. {members_2024_q4[:5]}")
    print(f"    'AAPL' in 2015-03-31: {'AAPL' in members_2015_q1}")
    print(f"    'AAPL' in 2024-12-31: {'AAPL' in members_2024_q4}")
    print(f"    'TSLA' in 2015-03-31: {'TSLA' in members_2015_q1}")
    print(f"    'TSLA' in 2024-12-31: {'TSLA' in members_2024_q4}")
    print(f"    'NVDA' in 2024-12-31: {'NVDA' in members_2024_q4}")

    # 2. Prices
    print("\n[2] Fetching AAPL prices (auto_adjust=True)...")
    aapl = prices.fetch_prices("AAPL", "2015-01-01", "2025-12-31")
    if aapl is None or aapl.empty:
        print("    FAIL: no AAPL data")
        return 1
    print(f"    AAPL: {len(aapl)} rows, {aapl.index[0].date()} to {aapl.index[-1].date()}")
    print(f"    First close: ${aapl['Close'].iloc[0]:.2f}")
    print(f"    Last close:  ${aapl['Close'].iloc[-1]:.2f}")
    print(f"    TR: {(aapl['Close'].iloc[-1]/aapl['Close'].iloc[0]-1)*100:.1f}%")

    # 3. SEC EDGAR shares
    print("\n[3] Fetching AAPL company-facts from SEC EDGAR...")
    aapl_cik = shares.ticker_to_cik("AAPL")
    print(f"    AAPL CIK: {aapl_cik}")
    facts = shares.fetch_company_facts("AAPL")
    if not facts:
        print("    FAIL: no facts")
        return 1
    print(f"    Got facts blob with {len(facts.get('facts', {}).get('dei', {}))} dei concepts, "
          f"{len(facts.get('facts', {}).get('us-gaap', {}))} us-gaap concepts")
    s_2015 = shares.shares_outstanding_at(facts, pd.Timestamp("2015-03-31"))
    s_2024 = shares.shares_outstanding_at(facts, pd.Timestamp("2024-12-31"))
    print(f"    Shares at 2015-03-31: {s_2015:,.0f}" if s_2015 else "    no shares at 2015-03-31")
    print(f"    Shares at 2024-12-31: {s_2024:,.0f}" if s_2024 else "    no shares at 2024-12-31")
    if s_2015:
        # Pre-2014 4:1 split, AAPL had ~5.8B shares end of 2014, so by 2015-03-31 ~5.8B
        # Post-2020 4:1 split, by end of 2024 should be ~15.1B
        print(f"    Sanity: 2015 should be ~5-6B (after 2014 7:1 split): {'OK' if 4e9 < s_2015 < 7e9 else 'CHECK'}")
        print(f"    Sanity: 2024 should be ~15B (after 2020 4:1 split): {'OK' if 14e9 < s_2024 < 16e9 else 'CHECK'}")

    # 4. Mini weights calc
    print("\n[4] Computing inverse-MC weights for a 5-ticker universe at 2024-12-31...")
    mini_universe = ["AAPL", "MSFT", "GOOGL", "JNJ", "PG"]
    mini_facts = {t: shares.fetch_company_facts(t) for t in mini_universe}
    mini_prices = {t: prices.fetch_prices(t, "2015-01-01", "2025-12-31") for t in mini_universe}
    overrides = shares.load_manual_overrides()
    failures: list[dict] = []
    w = W.compute_weights(
        pd.Timestamp("2024-12-31"), mini_universe, mini_facts, mini_prices, overrides, failures
    )
    print(f"    Got {len(w)} weights, sum = {w['weight'].sum():.6f}")
    print(w[["ticker", "shares", "price", "mc", "weight"]].to_string(index=False))
    if failures:
        print(f"    failures: {failures}")
    print(f"    Highest weight (smallest MC): {w.iloc[0]['ticker']} at {w.iloc[0]['weight']*100:.2f}%")
    print(f"    Lowest weight (largest MC):   {w.iloc[-1]['ticker']} at {w.iloc[-1]['weight']*100:.4f}%")
    # Verify ordering matches inverse MC ordering
    assert w["mc"].iloc[0] < w["mc"].iloc[-1], "FAIL: top weight should be smallest MC"
    print("    OK: smallest MC has largest weight")

    # 5. Trading calendar
    print("\n[5] Trading calendar...")
    cal = prices.trading_calendar("2015-01-01", "2025-12-31")
    print(f"    {len(cal)} trading days from {cal[0].date()} to {cal[-1].date()}")
    rebals = constituents.rebalance_dates("2015-01-01", "2025-12-31", cal)
    print(f"    {len(rebals)} quarterly rebalance dates")
    print(f"    First few: {[d.date() for d in rebals[:3]]}")
    print(f"    Last few:  {[d.date() for d in rebals[-3:]]}")

    print("\n[OK] Verification complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
