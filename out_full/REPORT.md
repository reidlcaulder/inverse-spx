# Inverse-Weighted S&P 500 Backtest — Full Window

**1996-01-02 → 2025-12-30**  (7,549 trading days, 30.0 years)

**Composition:**
- 1996-01-02 → 2024-12-31: WRDS / CRSP (gold-standard institutional data)
- 2025-01-01 → 2025-12-30: EDGAR / yfinance (CRSP doesn't have 2025 yet on Reid's subscription tier)

**Methodology:** pure 1/MC inverse weighting (no per-name cap), quarterly rebalance at last trading day of each calendar quarter, total return basis (auto_adjust=True for yfinance, CRSP `ret` for WRDS). Benchmark is SPY total return over the same window.

## Headline metrics

| Metric | Inverse-SPX | SPY | Inverse − SPY |
|---|---:|---:|---:|
| Total return | +6437.86% | +1783.30% | +4654.56% |
| CAGR | +14.96% | +10.28% | +4.67% |
| Annualized volatility | +21.93% | +19.28% | +2.66% |
| Sharpe (rf=0) | 0.75 | 0.60 | 0.14 |
| Max drawdown | -58.49% | -55.20% | -3.29% |

- Inverse-SPX max drawdown: -58.49% (2007-06-01 → 2009-03-09, recovered 2010-01-04)
- SPY max drawdown: -55.20% (2007-10-09 → 2009-03-09, recovered 2012-08-16)

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
| 2025 | +11.22% | +18.60% | -7.37% |

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
| 2025 | 65.379 | 18.833 |

## Top 5 drawdowns (Inverse-SPX)

| Peak | Trough | Recovery | Depth | Days to recover |
|---|---|---|---:|---:|
| 2007-06-01 | 2009-03-09 | 2010-01-04 | -58.49% | 301 |
| 2020-01-17 | 2020-03-23 | 2020-06-08 | -42.94% | 77 |
| 2002-04-17 | 2002-10-09 | 2003-05-15 | -42.72% | 218 |
| 1998-04-22 | 1998-10-08 | 1999-04-15 | -31.95% | 189 |
| 2011-05-10 | 2011-10-03 | 2012-02-16 | -25.78% | 136 |

## How the stitching works

WRDS-CRSP daily returns through 2024-12-31 are concatenated with EDGAR/yfinance daily returns from 2024-12-31 forward. Both feeds use total-return-adjusted prices (CRSP `ret` includes dividends; yfinance `auto_adjust=True` does the same). Cumulative values are recomputed from the concatenated daily return series, so the boundary is invisible in the resulting equity curve. The 2025 segment inherits any data-quality limitations of the EDGAR run (notably distorted concentration profiles for some multi-class issuers — see `out/REPORT.md` for detail), but historical headline-return divergence between the two methods has been small (<1 pp/year over 2015-2024).

## Limitations

- **Membership source.** Point-in-time S&P 500 constituents come from the fja05680/sp500 GitHub CSV, which begins 1996-01-02. That sets the earliest backtest start. Going earlier would require a different historical-membership source.
- **$100M market-cap floor on weight calculation.** Without a floor, pre-2008 CRSP shares-outstanding for some old delisted small-caps produced phantom $1-10M market caps that would have received 30-50% inverse weight (a single-name distortion that's clearly a data artifact, not a real signal). The floor drops names below $100M MC at each rebalance — ~3-5 names per quarter, mostly pre-2008. This is a sanity guard, not a strategy choice; documented in `lib/wrds_backtest.py`.
- **CUSIP-bridge gaps (WRDS path).** Reid's WRDS subscription doesn't include the CCM linkage table or `dsp500list`; we bridge ticker ↔ permno via `crsp.msenames` matched on (ticker, namedt..nameendt). Coverage is good (1081 unique permnos found across 1996-2024) but a few hundred ticker-rebalance pairs failed to map and were dropped.
- **2025 segment uses EDGAR/yfinance weights.** EDGAR's per-XBRL-fact share counts have known issues for multi-class issuers; cumulative-return impact has been small (<1 pp/year historically over 2015-2024) but per-name concentration in 2025 is less reliable than in the WRDS segment.
- **No transaction costs in headline numbers.** A 25 bps round-trip slippage scenario on the rebalanced fraction is computed in the source WRDS run (see `out_wrds/REPORT.md`). Quarterly rebalancing of a small-cap-tilted book is not free in reality.
- **No taxes.** Gross returns. Quarterly rebalancing in a taxable account would generate substantial short-term capital gains.

## Reproducibility

```
python inverse_spx_backtest_wrds.py --start 1996-01-02 --end 2024-12-31
python inverse_spx_backtest.py --start 2015-01-01 --end 2025-12-31
python inverse_spx_backtest_full.py
```