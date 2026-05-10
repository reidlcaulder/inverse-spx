# Inverse-Weighted S&P 500 Backtest — **WRDS / CRSP edition**

This run uses CRSP daily stock files and Compustat S&P 500 constituents — the gold-standard data sources, with proper delisting handling and no survivorship bias. Compare against the EDGAR/yfinance run at `out/REPORT.md`.

---

# Inverse-Weighted S&P 500 Backtest — 2015-01-01 to 2025-12-31

**Methodology**
- Universe: S&P 500 constituents at each rebalance date (point-in-time, fja05680/sp500)
- Weighting: pure mathematical inverse of cap-weight, `w_i = (1/MC_i) / Σ(1/MC_j)`, no per-name cap
- Rebalance: quarterly, last trading day of each calendar quarter (close-to-close, no look-ahead)
- Returns: total return (yfinance `auto_adjust=True`)
- Benchmark: SPY total return over the same window
- Risk-free rate for Sharpe: 0% (Sharpe-equivalent — disclosed)

## Headline metrics

| Metric | Inverse-SPX | SPY | Inverse − SPY |
|---|---:|---:|---:|
| Total return | +339.19% | +239.69% | +99.51% |
| CAGR | +15.96% | +13.01% | +2.94% |
| Annualized volatility | +19.30% | +17.61% | +1.69% |
| Sharpe (rf=0) | 0.86 | 0.78 | 0.08 |
| Max drawdown | -39.48% | -33.70% | -5.78% |

- Inverse-SPX max drawdown: -39.48% (2020-02-14 → 2020-03-23, recovered 2020-06-05)
- SPY max drawdown: -33.70% (2020-02-19 → 2020-03-23, recovered 2020-08-10)

### With 25 bps round-trip slippage applied per rebalance

Real-world execution on a small-cap-tilted book is not free. This scenario applies a 25 bps round-trip slippage charge against the rebalanced fraction (turnover) at each rebalance.

| Metric | Inverse-SPX (gross) | Inverse-SPX (slipped) | SPY |
|---|---:|---:|---:|
| Total return | +339.19% | +336.64% | +239.69% |
| CAGR | +15.96% | +15.89% | +13.01% |

## Calendar-year returns

| Year | Inverse-SPX | SPY | Spread |
|---|---:|---:|---:|
| 2015 | +3.43% | +1.25% | +2.18% |
| 2016 | +21.73% | +12.00% | +9.73% |
| 2017 | +26.41% | +21.70% | +4.71% |
| 2018 | -3.96% | -4.56% | +0.60% |
| 2019 | +34.00% | +31.22% | +2.78% |
| 2020 | +24.68% | +18.37% | +6.31% |
| 2021 | +33.71% | +28.75% | +4.97% |
| 2022 | -6.40% | -18.17% | +11.78% |
| 2023 | +19.48% | +26.19% | -6.71% |
| 2024 | +15.01% | +24.88% | -9.87% |

## Cumulative growth of $1 (year-end)

| Year-end | Inverse-SPX | SPY |
|---|---:|---:|
| 2015 | 1.034 | 1.013 |
| 2016 | 1.259 | 1.134 |
| 2017 | 1.591 | 1.380 |
| 2018 | 1.529 | 1.317 |
| 2019 | 2.048 | 1.728 |
| 2020 | 2.554 | 2.046 |
| 2021 | 3.415 | 2.634 |
| 2022 | 3.196 | 2.156 |
| 2023 | 3.819 | 2.720 |
| 2024 | 4.392 | 3.397 |

## Top 5 drawdowns (Inverse-SPX)

| Peak | Trough | Recovery | Depth | Days to recover |
|---|---|---|---:|---:|
| 2020-02-14 | 2020-03-23 | 2020-06-05 | -39.48% | 74 |
| 2022-03-29 | 2022-09-30 | 2023-02-01 | -18.44% | 124 |
| 2018-09-21 | 2018-12-24 | 2019-02-20 | -17.43% | 58 |
| 2020-06-08 | 2020-06-26 | 2020-11-09 | -16.46% | 136 |
| 2015-12-01 | 2016-02-11 | 2016-03-16 | -13.41% | 34 |

## Concentration profile (year-end weights)

| Year | N holdings | Top weight | Top-10 weight | % in bottom decile by MC |
|---|---:|---:|---:|---:|
| 2015 | 332 | 1.95% | 12.21% | 29.22% |
| 2016 | 350 | 2.38% | 12.09% | 28.24% |
| 2017 | 373 | 1.81% | 9.83% | 26.34% |
| 2018 | 388 | 2.18% | 10.08% | 25.95% |
| 2019 | 406 | 2.03% | 9.80% | 27.23% |
| 2020 | 418 | 1.64% | 9.86% | 28.84% |
| 2021 | 429 | 1.59% | 9.48% | 28.41% |
| 2022 | 438 | 1.63% | 10.04% | 28.96% |
| 2023 | 453 | 1.25% | 8.76% | 28.07% |
| 2024 | 475 | 1.08% | 7.87% | 28.26% |

## Turnover

- Average one-way turnover per rebalance: 5.83%
- Total rebalances: 41
- Annualized one-way turnover: 23.32% (quarterly × 4)
- Detail: see `out/turnover.csv`

## Failures (tickers dropped at rebalance)

- Total ticker-rebalance failures: 81 of 16418 pairs (0.5%)
- By reason:
  - `no_mc_at_rebal`: 81
- Full list: see `out/failures.csv`

## Limitations & caveats

1. **Survivorship bias.** Delisted small-caps that yfinance cannot price are dropped. Inverse-weighted strategies are *especially* sensitive: the smallest names get the largest weights, and the smallest names are also the most likely to delist (bankruptcy, acquisition, falling below S&P thresholds). This biases the backtest's return upward versus what an investor would actually have experienced. The number of dropped tickers per period is in `out/failures.csv`.
2. **~45-90 day fundamentals lag.** SEC requires 10-Q within ~40 days of period end. The cover-page CSO at our 2024-09-30 rebalance is typically the value reported in the Q2 10-Q filed around 2024-07-25. This is realistic — it's the data an investor would actually have available — but means market caps lag actual share counts by up to one quarter.
3. **Total CSO, not float-adjusted.** S&P 500 itself uses free-float market cap. We use total shares outstanding from XBRL filings. For names with concentrated insider holdings, this overstates MC and slightly under-weights them in the inverse scheme.
4. **No transaction costs in headline numbers.** The slippage-adjusted scenario above applies a flat 25 bps round-trip charge against turnover. Actual execution costs on a small-cap-tilted book during stress periods could be materially higher.
5. **No taxes.** Quarterly rebalancing of a turnover-heavy strategy in a taxable account would generate substantial short-term capital gains.
6. **fja05680 is a community-maintained constituent list, not S&P-licensed.** Spot checks against known additions/deletions are reasonable, but treat exact membership as approximate.
7. **yfinance occasional split mis-application.** Spot-check NVDA 10:1 (June 2024), AAPL 4:1 (Aug 2020), TSLA 3:1 (Aug 2022), AMZN 20:1 (June 2022), GOOGL 20:1 (July 2022).

## Reproducibility

```
python inverse_spx_backtest.py --start 2015-01-01 --end 2025-12-31
```
Cache files under `data/cache/`. Companion CSVs in `out/`.
