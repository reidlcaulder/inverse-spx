# inverse-spx

Backtest of an **inverse-weighted S&P 500** index — the same constituents as the real S&P 500, but with weights inversely proportional to market cap (so the smallest holding gets the largest weight). Quarterly rebalanced, total return, vs SPY benchmark, 2015-2025.

The strategy is the literal mathematical opposite of cap-weighting: where SPX uses `w_i = MC_i / Σ MC_j`, this index uses `w_i = (1/MC_i) / Σ(1/MC_j)`, no per-name cap. The point is to surface what a cap-weighted index downplays — small caps get amplified, mega caps essentially disappear.

## Headline result (10-year window)

Two independent backtests, both pointing the same direction:

| Run | Window | Inverse-SPX | SPY | Spread |
|---|---|---:|---:|---:|
| **WRDS / CRSP** (gold standard) | 2015 – 2024 | +339% (CAGR 16.0%) | +240% (CAGR 13.0%) | +99 pts |
| EDGAR / yfinance (free) | 2015 – 2025 | +368% (CAGR 15.1%) | +303% (CAGR 13.5%) | +66 pts |

Sharpe is comparable (~0.85 vs 0.80) — the inverse strategy beat SPY in cumulative return with similar risk-adjusted performance. The gap is concentrated in 2015-2017 (small-cap rally) and 2022 (mega-cap drawdown). It gave back ground in 2023-2024 during the Mag-7 surge.

Full reports:
- [out_wrds/REPORT.md](out_wrds/REPORT.md) — primary, CRSP-backed
- [out/REPORT.md](out/REPORT.md) — free-data baseline

## Why two runs?

The free data path (SEC EDGAR shares-outstanding × yfinance prices) produced clean cumulative returns but distorted *concentration profiles* — a few multi-class issuers had bad XBRL share counts that gave them implausible 10%+ inverse weights. CRSP via WRDS gives the right shape (top weight ~1-2%, bottom-decile share ~30%), and an iShares IVV regulatory-filing diagnostic confirmed the WRDS numbers are accurate. The EDGAR run is kept as a free alternative for anyone without WRDS — the cumulative return story holds, just don't trust the concentration table beyond the directional read.

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

- **Universe** — S&P 500 constituents at each quarter-end, point-in-time
  - EDGAR run: [fja05680/sp500](https://github.com/fja05680/sp500) community CSV
  - WRDS run: Compustat `idxcst_his` (gvkey-based), bridged to CRSP permno via CUSIP-8 (Reid's subscription doesn't include the CCM linkage table, so a CUSIP bridge is used)
- **Weighting** — pure 1/MC, normalized to sum to 1, no per-name cap
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
├── out/                            # EDGAR/yfinance run outputs (REPORT.md + CSVs)
└── out_wrds/                       # WRDS/CRSP run outputs
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
