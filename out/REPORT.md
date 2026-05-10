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
| Total return | +368.31% | +302.73% | +65.59% |
| CAGR | +15.08% | +13.51% | +1.57% |
| Annualized volatility | +19.49% | +17.79% | +1.70% |
| Sharpe (rf=0) | 0.82 | 0.80 | 0.02 |
| Max drawdown | -39.86% | -33.72% | -6.15% |

- Inverse-SPX max drawdown: -39.86% (2020-02-20 → 2020-03-23, recovered 2020-06-08)
- SPY max drawdown: -33.72% (2020-02-19 → 2020-03-23, recovered 2020-08-10)

### With 25 bps round-trip slippage applied per rebalance

Real-world execution on a small-cap-tilted book is not free. This scenario applies a 25 bps round-trip slippage charge against the rebalanced fraction (turnover) at each rebalance.

| Metric | Inverse-SPX (gross) | Inverse-SPX (slipped) | SPY |
|---|---:|---:|---:|
| Total return | +368.31% | +362.78% | +302.73% |
| CAGR | +15.08% | +14.96% | +13.51% |

## Calendar-year returns

| Year | Inverse-SPX | SPY | Spread |
|---|---:|---:|---:|
| 2015 | +12.88% | +1.29% | +11.59% |
| 2016 | +25.21% | +12.00% | +13.21% |
| 2017 | +18.75% | +21.71% | -2.96% |
| 2018 | +0.78% | -4.57% | +5.35% |
| 2019 | +34.60% | +31.22% | +3.37% |
| 2020 | +20.97% | +18.33% | +2.64% |
| 2021 | +26.93% | +28.73% | -1.80% |
| 2022 | -9.45% | -18.18% | +8.72% |
| 2023 | +17.03% | +26.18% | -9.15% |
| 2024 | +13.68% | +24.89% | -11.21% |
| 2025 | +11.22% | +18.60% | -7.37% |

## Cumulative growth of $1 (year-end)

| Year-end | Inverse-SPX | SPY |
|---|---:|---:|
| 2015 | 1.129 | 1.013 |
| 2016 | 1.413 | 1.134 |
| 2017 | 1.678 | 1.381 |
| 2018 | 1.691 | 1.318 |
| 2019 | 2.277 | 1.729 |
| 2020 | 2.754 | 2.046 |
| 2021 | 3.496 | 2.634 |
| 2022 | 3.165 | 2.155 |
| 2023 | 3.704 | 2.719 |
| 2024 | 4.211 | 3.396 |
| 2025 | 4.683 | 4.027 |

## Top 5 drawdowns (Inverse-SPX)

| Peak | Trough | Recovery | Depth | Days to recover |
|---|---|---|---:|---:|
| 2020-02-20 | 2020-03-23 | 2020-06-08 | -39.86% | 77 |
| 2022-03-29 | 2022-09-30 | 2023-07-19 | -20.24% | 292 |
| 2018-09-20 | 2018-12-24 | 2019-02-15 | -18.47% | 53 |
| 2024-12-02 | 2025-04-08 | 2025-07-23 | -16.90% | 106 |
| 2020-06-08 | 2020-06-26 | 2020-11-09 | -16.62% | 136 |

## Concentration profile (year-end weights)

| Year | N holdings | Top weight | Top-10 weight | % in bottom decile by MC |
|---|---:|---:|---:|---:|
| 2015 | 365 | 12.72% | 42.10% | 58.21% |
| 2016 | 386 | 12.04% | 39.05% | 54.81% |
| 2017 | 400 | 13.09% | 40.50% | 55.92% |
| 2018 | 414 | 10.29% | 35.53% | 52.19% |
| 2019 | 428 | 12.06% | 34.21% | 50.08% |
| 2020 | 439 | 13.47% | 28.50% | 46.34% |
| 2021 | 450 | 14.01% | 28.21% | 44.83% |
| 2022 | 464 | 11.63% | 25.23% | 43.09% |
| 2023 | 471 | 11.88% | 24.28% | 41.39% |
| 2024 | 478 | 10.63% | 22.36% | 40.58% |
| 2025 | 480 | 10.67% | 21.69% | 40.56% |

## Turnover

- Average one-way turnover per rebalance: 10.80%
- Total rebalances: 45
- Annualized one-way turnover: 43.18% (quarterly × 4)
- Detail: see `out/turnover.csv`

## Failures (tickers dropped at rebalance)

- Total ticker-rebalance failures: 3217 of 22470 pairs (14.3%)
- By reason:
  - `no_shares`: 3216
  - `no_price`: 1
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
