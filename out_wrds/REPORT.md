# Inverse-Weighted S&P 500 Backtest — **WRDS / CRSP edition**

This run uses CRSP daily stock files and Compustat S&P 500 constituents — the gold-standard data sources, with proper delisting handling and no survivorship bias. Compare against the EDGAR/yfinance run at `out/REPORT.md`.

---

# Inverse-Weighted S&P 500 Backtest — 1996-01-01 to 2024-12-31

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
| Total return | +5778.07% | +1487.98% | +4290.09% |
| CAGR | +15.08% | +10.01% | +5.08% |
| Annualized volatility | +22.05% | +19.27% | +2.78% |
| Sharpe (rf=0) | 0.75 | 0.59 | 0.16 |
| Max drawdown | -58.49% | -55.20% | -3.29% |

- Inverse-SPX max drawdown: -58.49% (2007-06-01 → 2009-03-09, recovered 2010-01-04)
- SPY max drawdown: -55.20% (2007-10-09 → 2009-03-09, recovered 2012-08-16)

### With 25 bps round-trip slippage applied per rebalance

Real-world execution on a small-cap-tilted book is not free. This scenario applies a 25 bps round-trip slippage charge against the rebalanced fraction (turnover) at each rebalance.

| Metric | Inverse-SPX (gross) | Inverse-SPX (slipped) | SPY |
|---|---:|---:|---:|
| Total return | +5778.07% | +5605.07% | +1487.98% |
| CAGR | +15.08% | +14.97% | +10.01% |

## Calendar-year returns

| Year | Inverse-SPX | SPY | Spread |
|---|---:|---:|---:|
| 1996 | +17.31% | +22.55% | -5.25% |
| 1997 | +33.08% | +33.48% | -0.40% |
| 1998 | -1.28% | +28.69% | -29.96% |
| 1999 | +29.70% | +20.39% | +9.31% |
| 2000 | +15.87% | -9.73% | +25.60% |
| 2001 | +32.18% | -11.75% | +43.94% |
| 2002 | -11.98% | -21.59% | +9.60% |
| 2003 | +70.48% | +28.18% | +42.30% |
| 2004 | +26.16% | +10.70% | +15.46% |
| 2005 | +25.89% | +4.83% | +21.06% |
| 2006 | +11.64% | +15.85% | -4.20% |
| 2007 | -2.01% | +5.14% | -7.15% |
| 2008 | -34.21% | -36.81% | +2.60% |
| 2009 | +69.26% | +26.37% | +42.90% |
| 2010 | +25.87% | +15.06% | +10.81% |
| 2011 | -0.51% | +1.89% | -2.40% |
| 2012 | +28.07% | +15.99% | +12.08% |
| 2013 | +43.46% | +32.31% | +11.15% |
| 2014 | +14.39% | +13.46% | +0.93% |
| 2015 | -6.44% | +1.25% | -7.69% |
| 2016 | +21.01% | +12.00% | +9.01% |
| 2017 | +15.02% | +21.70% | -6.68% |
| 2018 | -7.15% | -4.56% | -2.60% |
| 2019 | +27.56% | +31.22% | -3.66% |
| 2020 | +18.60% | +18.37% | +0.23% |
| 2021 | +29.69% | +28.75% | +0.94% |
| 2022 | -10.86% | -18.17% | +7.31% |
| 2023 | +7.75% | +26.19% | -18.44% |
| 2024 | +10.29% | +24.88% | -14.60% |

## Cumulative growth of $1 (year-end)

| Year-end | Inverse-SPX | SPY |
|---|---:|---:|
| 1996 | 1.173 | 1.226 |
| 1997 | 1.561 | 1.636 |
| 1998 | 1.541 | 2.105 |
| 1999 | 1.999 | 2.534 |
| 2000 | 2.316 | 2.288 |
| 2001 | 3.062 | 2.019 |
| 2002 | 2.695 | 1.583 |
| 2003 | 4.594 | 2.029 |
| 2004 | 5.796 | 2.246 |
| 2005 | 7.296 | 2.355 |
| 2006 | 8.145 | 2.728 |
| 2007 | 7.982 | 2.868 |
| 2008 | 5.251 | 1.812 |
| 2009 | 8.888 | 2.290 |
| 2010 | 11.188 | 2.635 |
| 2011 | 11.131 | 2.685 |
| 2012 | 14.255 | 3.114 |
| 2013 | 20.451 | 4.120 |
| 2014 | 23.395 | 4.675 |
| 2015 | 21.888 | 4.733 |
| 2016 | 26.486 | 5.301 |
| 2017 | 30.464 | 6.452 |
| 2018 | 28.285 | 6.158 |
| 2019 | 36.080 | 8.080 |
| 2020 | 42.792 | 9.565 |
| 2021 | 55.494 | 12.314 |
| 2022 | 49.465 | 10.077 |
| 2023 | 53.297 | 12.716 |
| 2024 | 58.781 | 15.880 |

## Top 5 drawdowns (Inverse-SPX)

| Peak | Trough | Recovery | Depth | Days to recover |
|---|---|---|---:|---:|
| 2007-06-01 | 2009-03-09 | 2010-01-04 | -58.49% | 301 |
| 2020-01-17 | 2020-03-23 | 2020-06-08 | -42.94% | 77 |
| 2002-04-17 | 2002-10-09 | 2003-05-15 | -42.72% | 218 |
| 1998-04-22 | 1998-10-08 | 1999-04-15 | -31.95% | 189 |
| 2011-05-10 | 2011-10-03 | 2012-02-16 | -25.78% | 136 |

## Concentration profile (year-end weights)

| Year | N holdings | Top weight | Top-10 weight | % in bottom decile by MC |
|---|---:|---:|---:|---:|
| 1996 | 392 | 4.86% | 25.58% | 51.09% |
| 1997 | 400 | 6.46% | 34.50% | 55.15% |
| 1998 | 400 | 5.96% | 27.32% | 50.90% |
| 1999 | 402 | 6.38% | 27.65% | 50.70% |
| 2000 | 395 | 6.59% | 29.48% | 52.43% |
| 2001 | 416 | 2.39% | 14.74% | 37.95% |
| 2002 | 423 | 2.97% | 15.17% | 38.59% |
| 2003 | 426 | 1.60% | 11.98% | 34.60% |
| 2004 | 428 | 13.18% | 28.29% | 45.97% |
| 2005 | 424 | 6.85% | 23.83% | 43.80% |
| 2006 | 427 | 12.23% | 28.46% | 46.38% |
| 2007 | 430 | 7.22% | 21.99% | 43.86% |
| 2008 | 440 | 3.99% | 19.68% | 43.74% |
| 2009 | 445 | 7.14% | 19.76% | 38.34% |
| 2010 | 442 | 6.63% | 20.59% | 39.27% |
| 2011 | 437 | 5.85% | 19.11% | 38.68% |
| 2012 | 437 | 6.84% | 16.82% | 35.86% |
| 2013 | 434 | 1.80% | 9.24% | 29.02% |
| 2014 | 435 | 1.51% | 9.82% | 29.90% |
| 2015 | 436 | 1.63% | 11.79% | 33.08% |
| 2016 | 435 | 1.39% | 11.29% | 32.02% |
| 2017 | 432 | 1.73% | 11.95% | 32.25% |
| 2018 | 442 | 2.02% | 10.88% | 30.94% |
| 2019 | 441 | 1.47% | 9.54% | 30.05% |
| 2020 | 445 | 1.47% | 10.94% | 32.75% |
| 2021 | 447 | 1.44% | 11.19% | 31.20% |
| 2022 | 439 | 2.31% | 11.30% | 31.68% |
| 2023 | 443 | 3.19% | 12.45% | 32.86% |
| 2024 | 443 | 1.07% | 8.89% | 30.33% |

## Turnover

- Average one-way turnover per rebalance: 10.30%
- Total rebalances: 117
- Annualized one-way turnover: 41.20% (quarterly × 4)
- Detail: see `out/turnover.csv`

## Failures (tickers dropped at rebalance)

- Total ticker-rebalance failures: 566 of 50622 pairs (1.1%)
- By reason:
  - `no_mc_at_rebal`: 329
  - `mc_below_floor_100000000`: 237
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
python inverse_spx_backtest.py --start 1996-01-01 --end 2024-12-31
```
Cache files under `data/cache/`. Companion CSVs in `out/`.
