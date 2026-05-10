# inverse-spx

Backtest of an **inverse-weighted S&P 500** index — the same constituents as the real S&P 500, but with weights inversely proportional to market cap (so the smallest holding gets the largest weight). Quarterly rebalanced, total return, vs SPY benchmark, 2015-2025.

The strategy is the literal mathematical opposite of cap-weighting: where SPX uses `w_i = MC_i / Σ MC_j`, this index uses `w_i = (1/MC_i) / Σ(1/MC_j)`, no per-name cap. The point is to surface what a cap-weighted index downplays — small caps get amplified, mega caps essentially disappear.

## Headline result (1996 – 2025, 30 years)

Stitched run combining WRDS/CRSP for 1996-2024 with EDGAR/yfinance for 2025:

| Metric | **Inverse-SPX** | SPY | Spread |
|---|---:|---:|---:|
| Total return (30y) | **+6,438%** | +1,783% | +4,655 pts |
| CAGR | **+14.96%** | +10.28% | +4.67 pts |
| Annualized volatility | 21.93% | 19.28% | +2.66 pts |
| **Sharpe (rf=0)** | **0.75** | 0.60 | +0.14 |
| Max drawdown | -58.49% | -55.20% | -3.29 pts |

Inverse-weighted S&P 500 beat the cap-weighted index by ~4.7 percentage points per year over 30 years, with similar volatility and a slightly worse drawdown — leading to a meaningfully higher Sharpe ratio. The gap accumulated in three distinct regimes: 2000-2003 dot-com bust (small caps held up while mega-caps crashed), 2003-2007 small-cap rally, and 2009-2014 post-crisis recovery. The strategy lagged in 2017 and 2023-2025 (Mag-7 dominance).

Full reports:
- **[out_full/REPORT.md](out_full/REPORT.md)** — primary, 30-year stitched
- [out_wrds/REPORT.md](out_wrds/REPORT.md) — WRDS-only, 1996-2024
- [out/REPORT.md](out/REPORT.md) — EDGAR-only, 2015-2025

## Why three runs?

- **`out_full/`** is the primary deliverable: 30-year stitched (WRDS for 1996-2024, EDGAR for 2025).
- **`out_wrds/`** is the source for the historical bulk. WRDS/CRSP provides clean point-in-time prices and total returns including delisted names.
- **`out/`** is a free-data baseline. SEC EDGAR shares-outstanding × yfinance prices, full 2015-2025 window. Useful when WRDS isn't available, but its concentration profile is distorted by per-class XBRL share counts on multi-class issuers (an iShares IVV regulatory-filing diagnostic in `lib/etf_weights.py` confirmed this). Cumulative-return divergence from WRDS over 2015-2024 is small (<1 pp/year), so the EDGAR run is also what we use for the 2025 tail in the stitched run.

Membership for both WRDS and EDGAR comes from the [fja05680/sp500](https://github.com/fja05680/sp500) GitHub CSV — point-in-time including historical exits. This was important because Reid's WRDS subscription's `comp.idxcst_his` table contains only current S&P 500 members; using it as a membership source would have produced severe survivorship bias.

## Setup

```bash
git clone https://github.com/reidlcaulder/inverse-spx.git
cd inverse-spx
pip install -e .
cp .env.example .env
# Edit .env to set SEC_EDGAR_USER_AGENT_EMAIL (and WRDS_USERNAME if applicable)
```

`SEC_EDGAR_USER_AGENT_EMAIL` is required even for the free-data run — SEC's fair-access policy requires a real contact email in the User-Agent header.

## Run

### Full stitched backtest (primary, 30 years)

Requires both WRDS and EDGAR runs to have completed first.

```bash
python inverse_spx_backtest_wrds.py --start 1996-01-01 --end 2024-12-31
python inverse_spx_backtest.py     --start 2015-01-01 --end 2025-12-31
python inverse_spx_backtest_full.py
# output: out_full/REPORT.md
```

### EDGAR / yfinance (free, ~25-40 min cold cache)

```bash
python inverse_spx_backtest.py --start 2015-01-01 --end 2025-12-31
# output: out/REPORT.md + companion CSVs
```

### WRDS / CRSP (requires subscription)

Requires a WRDS account with CRSP access. One-time setup of `.pgpass` (per [WRDS docs](https://wrds-www.wharton.upenn.edu/pages/support/the-wrds-cloud/setting-pgpass-file/)) so connections are passwordless:

```bash
pip install -e .[wrds]
# In a real terminal (not Claude Code), run once interactively to set up .pgpass:
python -c "import wrds; db = wrds.Connection(wrds_username='YOUR_USERNAME'); db.close()"
# Answer "yes" when it offers to save the .pgpass file.

python inverse_spx_backtest_wrds.py --start 2015-01-01 --end 2025-12-31
# output: out_wrds/REPORT.md + companion CSVs
```

CRSP refreshes annually; right now the daily stock file goes through 2024-12-31, so the WRDS run is bounded there.

### Sanity check before either run

```bash
python verify.py
# Verifies: fja05680 constituents fetch, AAPL price/shares roundtrip, weight calc on a 5-ticker mini-universe
```

## Methodology

- **Universe** — S&P 500 constituents at each quarter-end, point-in-time, from the [fja05680/sp500](https://github.com/fja05680/sp500) community CSV (the only practical free source that includes historical exits with their leave-month suffix). Earliest snapshot: 1996-01-02. The WRDS path maps these tickers to CRSP permnos via `crsp.msenames` matched on (ticker, namedt..nameendt) ranges.
- **Weighting** — pure 1/MC, normalized to sum to 1, no per-name cap. The WRDS path applies a $100M minimum market-cap floor at each rebalance to filter out a small number of pre-2008 phantom-data permnos (where stale CRSP shares-outstanding for delisted small-caps produced impossible <$10M MCs that would otherwise have received 30-50% inverse weight). The floor drops 3-5 names per quarter, almost all pre-2008.
- **Rebalance** — last trading day of each calendar quarter; weights set at close, applied next day forward (no look-ahead)
- **Returns** — total return: `auto_adjust=True` for yfinance / `ret` field for CRSP (both fold dividends into the price series)
- **Mid-quarter delisting** — EDGAR run carries forward last close until next rebalance drops the position. WRDS run additionally applies CRSP `dlret` on the delisting date when populated.

## Project layout

```
inverse-spx/
├── inverse_spx_backtest.py         # EDGAR/yfinance orchestrator
├── inverse_spx_backtest_wrds.py    # WRDS/CRSP orchestrator
├── verify.py                       # single-ticker smoke tests
├── lib/
│   ├── config.py                   # env-var config (SEC UA email, WRDS username)
│   ├── constituents.py             # fja05680 fetch + point-in-time membership
│   ├── ticker_aliases.py           # historical→current symbol remap (FB→META, etc.)
│   ├── shares.py                   # SEC EDGAR XBRL shares outstanding
│   ├── prices.py                   # yfinance OHLCV with delta-cache
│   ├── weights.py                  # inverse-MC weighting
│   ├── backtest.py                 # daily TR portfolio simulator (price-based)
│   ├── benchmark.py                # SPY total return
│   ├── metrics.py                  # CAGR, vol, Sharpe, MDD, turnover, drawdowns
│   ├── report.py                   # REPORT.md generator
│   ├── wrds_data.py                # CRSP + Compustat queries (with CUSIP bridge)
│   ├── wrds_backtest.py            # returns-based simulator with delisting handling
│   └── etf_weights.py              # parses iShares N-Q filings for actual IVV weights
├── data/
│   ├── cache/                      # gitignored — parquet/JSON caches
│   └── manual_overrides/           # CSV fallbacks for SEC data gaps
├── inverse_spx_backtest_full.py    # Stitch WRDS + EDGAR into single 1996-present series
├── out/                            # EDGAR/yfinance 2015-2025
├── out_wrds/                       # WRDS/CRSP 1996-2024
└── out_full/                       # Stitched 1996-2025 (primary deliverable)
```

## Known limitations

The full caveats live in each run's REPORT.md. Highlights:

1. **Survivorship bias on the EDGAR run** — yfinance has spotty history for delisted small-caps; we drop them, biasing returns upward. Inverse weighting amplifies this (the smallest names get the largest weights, and the smallest names are most likely to delist). The WRDS run mostly fixes this since CRSP retains delisted history. ~14% of ticker-rebalance pairs were dropped in EDGAR vs ~0.5% in WRDS.
2. **CRSP doesn't have 2025 yet** — typical institutional subscription cadence. The WRDS run ends 2024-12-31; for 2025 use the EDGAR run.
3. **WRDS without CCM** — Reid's WRDS subscription doesn't include the CCM (CRSP↔Compustat) linkage table, so the WRDS run bridges via CUSIP-8 (`comp.security.cusip[:8]` → `crsp.msenames.ncusip`). Coverage is good (~491 unique permnos found) but imperfect; a few delisted small-caps may be missing.
4. **Multi-class share quirks** — EDGAR's `dei:EntityCommonStockSharesOutstanding` reports per-class for dual-class issuers (GOOGL/GOOG, BRK.A/BRK.B). The fallback chain in `lib/shares.py` handles most cases but is the most likely source of any remaining EDGAR weight oddities.
5. **No transaction costs in headline numbers** — both runs include a separate slippage-adjusted scenario (25 bps round-trip on rebalanced fraction) for honesty. Quarterly rebalancing of a small-cap-tilted book is not free in reality.
6. **No taxes** — gross returns. Quarterly rebalancing in a taxable account would generate substantial short-term capital gains.

## Validating the weights

Both backtests' concentration profiles were cross-checked against actual iShares Core S&P 500 (IVV) regulatory filings parsed from SEC EDGAR — see `lib/etf_weights.py`. A diagnostic at 2017-Q2 showed:

| Source | Top inverse weight | Top-10 inverse weight | Bottom-decile share |
|---|---:|---:|---:|
| IVV N-Q filing (truth) | 1.81% | 9.49% | 29.88% |
| WRDS / CRSP | 2.01% | ~10% | 26.34% |
| EDGAR / yfinance | 13.09% | ~40% | 55.92% |

Cumulative-return outcomes nonetheless agree within ~4 percentage points over 10 years between EDGAR and WRDS — so the EDGAR run is wrong on weights but mostly right on aggregate returns (the bad weights cancelled rather than systematically biasing).

## License

MIT.
