# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Backtest of an **inverse-weighted S&P 500** index, 2015 onward. Where the actual index uses `w_i = MC_i / ΣMC`, this one uses `w_i = (1/MC_i) / Σ(1/MC_j)`, no per-name cap. Quarterly rebalanced, total return, vs SPY benchmark. Output is markdown reports + CSVs in `out/` (EDGAR run) and `out_wrds/` (WRDS run).

User-facing description: see [README.md](README.md). Don't duplicate it here.

## Three runs, one stitched output

| Run | Source | Window | Output |
|---|---|---|---|
| **Stitched** (primary) | WRDS + EDGAR | 1996-2025 | `out_full/REPORT.md` |
| WRDS / CRSP | Compustat + CRSP | 1996-2024 | `out_wrds/REPORT.md` |
| EDGAR / yfinance | SEC EDGAR + yfinance | 2015-2025 | `out/REPORT.md` |

The stitched run uses WRDS daily total returns through 2024-12-31 (the latest CRSP cut on Reid's subscription) and appends EDGAR/yfinance daily returns from 2025-01-02 onward. The EDGAR data path was validated against actual iShares IVV regulatory filings (`lib/etf_weights.py`) — its cumulative returns track WRDS within ~1 pp/year, though its concentration profile is distorted by per-class XBRL share counts on multi-class issuers.

## Running

```
pip install -e .                  # base deps
pip install -e .[wrds]            # add wrds package for the WRDS path

# Required: copy .env.example to .env and set SEC_EDGAR_USER_AGENT_EMAIL.
# Optional: set WRDS_USERNAME there if you'll run the WRDS path.

python verify.py                                                          # smoke test
python inverse_spx_backtest.py --start 2015-01-01 --end 2025-12-31         # EDGAR run
python inverse_spx_backtest_wrds.py --start 2015-01-01 --end 2025-12-31    # WRDS run
```

Cold cache: 25-40 min for EDGAR (rate-limited by SEC and yfinance), ~5-10 min for WRDS (a few SQL queries). Warm cache: 1-2 min for either.

`verify.py` is the fastest way to confirm the data layer works after editing — runs single-ticker fetches end-to-end against AAPL.

## Architecture: pipeline stages

The orchestrators ([inverse_spx_backtest.py](inverse_spx_backtest.py) and [inverse_spx_backtest_wrds.py](inverse_spx_backtest_wrds.py)) call modules under `lib/` in a strict pipeline. Each stage caches its output so re-runs are fast.

### EDGAR / yfinance path

1. **Constituents** ([lib/constituents.py](lib/constituents.py)) — fetches the [fja05680/sp500](https://github.com/fja05680/sp500) CSV via the GitHub API. Filename rolls over monthly with embedded date suffix; `_find_latest_dated_file()` picks the newest. Returns long-format `date, ticker`. `constituents_at(date, history)` forward-fills membership from the most recent snapshot ≤ date.
2. **Trading calendar + rebalance dates** — derived from SPY's price index so non-trading days are excluded automatically. `rebalance_dates()` returns last trading day of each calendar quarter.
3. **SEC EDGAR shares facts** ([lib/shares.py](lib/shares.py)) — one HTTP call per ticker to `data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json`. Returns the entire XBRL fact history. Rate-limited at 0.12s between calls. `shares_outstanding_at(facts, asof)` walks `dei:EntityCommonStockSharesOutstanding` → `us-gaap:CommonStockSharesOutstanding` → `us-gaap:CommonStockSharesIssued` and picks the entry with the latest `end` ≤ asof.
4. **Prices** ([lib/prices.py](lib/prices.py)) — yfinance with `auto_adjust=True` (folds in splits and dividends). Delta-cache: subsequent runs only fetch dates after `last_date`.
5. **Weights** ([lib/weights.py](lib/weights.py)) — at each rebalance: `MC = shares × price`, then `weight = (1/MC) / Σ(1/MC)`. Drops any ticker missing shares or price; logs the failure.
6. **Simulate + report** ([lib/backtest.py](lib/backtest.py), [lib/report.py](lib/report.py)) — strict close-to-close TR portfolio simulator (no look-ahead — see invariant below), then markdown report + CSVs.

### WRDS / CRSP path

1. **Constituents** ([lib/wrds_data.py](lib/wrds_data.py) `fetch_sp500_constituents`) — uses fja05680/sp500 GitHub CSV (point-in-time including historical exits) and maps each historical ticker to a permno via `crsp.msenames` matched on (ticker, namedt..nameendt). **Important:** we do NOT use `comp.idxcst_his` because on Reid's subscription it contains only current S&P 500 members (~503 rows, all with null thru-date) — using it would cause severe survivorship bias.
2. **Daily data** ([lib/wrds_data.py](lib/wrds_data.py) `fetch_daily_data`) — single CRSP `dsf` query for prices, shares, total returns. Stores as long-format parquet (~5M rows for 1996-2024).
3. **Delistings** (`fetch_delistings`) — CRSP `dsedelist` events with `dlret`. Some entries have null `dlret` because CRSP populates it inconsistently across delisting types. Applied in `apply_delisting_returns` (vectorized via per-permno date arrays + binary search).
4. **Weights** ([lib/wrds_backtest.py](lib/wrds_backtest.py) `compute_inverse_weights`) — pure 1/MC, with a $100M minimum market-cap floor as a sanity guard against pre-2008 phantom data (stale CRSP shares-outstanding for delisted small-caps that produced impossible <$10M MCs and would otherwise have received 30-50% inverse weight). The floor drops 3-5 names per quarter, almost all pre-2008. Set `mc_floor=0` to disable.
5. **Simulate** ([lib/wrds_backtest.py](lib/wrds_backtest.py) `run_backtest_returns`) — returns-based simulator using CRSP's `ret` field directly (no need to reconstruct returns from prices). Reuses `lib/report.py` for output.

### Diagnostic / cross-check

[lib/etf_weights.py](lib/etf_weights.py) parses iShares Core S&P 500 (IVV) holdings out of N-Q regulatory filings on SEC EDGAR. Used as ground truth for validating the EDGAR vs WRDS concentration profiles. Not part of the production backtest.

### Stitched run

[inverse_spx_backtest_full.py](inverse_spx_backtest_full.py) loads `out_wrds/daily_returns.csv` and `out/daily_returns.csv`, concatenates WRDS through 2024-12-31 with EDGAR daily returns from 2025-01-02 onward, and writes `out_full/REPORT.md` covering the full window. No new data fetching — just a re-aggregation of the two source runs.

## Critical invariants (don't break these)

- **No look-ahead in either simulator.** At rebalance day `d`, holdings are set using *close* prices on `d`. The first daily return contribution from new holdings is on `d+1`. See [lib/backtest.py](lib/backtest.py) `run_backtest()` and [lib/wrds_backtest.py](lib/wrds_backtest.py) `run_backtest_returns()`.
- **The "T0" rebalance.** Both orchestrators prepend the first trading day of the window to the rebal list so the portfolio is initialized on day 0 from `weights_per_rebal[t0]`. There are 45 rebalance dates total (1 T0 + 44 quarter-ends) for a 2015-2025 EDGAR window.
- **Ticker alias remap order (EDGAR path).** `constituents_at()` returns historical symbols (e.g. `FB` in 2015). The orchestrator passes them through `ticker_aliases.remap()` (e.g. `FB → META`) *before* SEC and yfinance lookups. Aliases that return `None` (acquired with no successor) are dropped from the universe. Adding new renames goes in [lib/ticker_aliases.py](lib/ticker_aliases.py).
- **Delisted tickers carry a `-YYYYMM` suffix in fja05680.** [constituents.py](lib/constituents.py) `_strip_delisted_suffix()` strips it before returning. Don't bypass.
- **Manual override CSV is the ground truth for shares.** When `data/manual_overrides/shares_outstanding.csv` has an entry for `(date, ticker)`, [weights.py](lib/weights.py) uses it instead of SEC. Use this for known holdouts where SEC EDGAR is missing or wrong.
- **No yfinance current-snapshot fallback for shares.** Tempting but wrong: a ticker whose 2015 share count is 30M and today's is 100M would get massively misweighted in a 2015 rebalance. We drop instead. Don't add this fallback.
- **Compustat schema gotchas.** `comp.idxcst_his` columns are `from`/`thru` (SQL reserved words — quote them). `crsp.msenames` end column is `nameendt` (not `nameenddt`). Date columns from psycopg2 come back as Python strings — wrap in `pd.to_datetime()` after the query. SPY ETF in CRSP is `permno = 84398`. The full set of accessible vs gated tables on Reid's subscription is documented in `~/.claude/CLAUDE.md`.

## Caching layout

```
data/cache/
  constituents.parquet            # fja05680 long-format — refreshed only with --refresh-constituents
  ticker_cik_map.json             # SEC ticker → CIK (one-time fetch)
  sec_facts/{TICKER}.json         # full XBRL company-facts blob, ~50-200 KB each
  prices/{TICKER}.parquet         # full daily OHLCV, ~150 KB each
  weights/{date}.parquet          # recomputed cheaply on every run
  wrds_constituents.parquet       # WRDS path: long-format date,permno,ticker
  wrds_daily.parquet              # WRDS path: full daily price/shares/return panel
  wrds_delistings.parquet         # WRDS path: delisting events
  wrds_spy.parquet                # WRDS path: SPY benchmark series
  etf_filings/{accession}.txt     # Diagnostic path: IVV N-Q stripped HTML
```

Empty parquet at `prices/{TICKER}.parquet` is a *valid* cache state — it means "yfinance has no data for this ticker", and we won't retry. To force a retry, delete the file or use `--refresh-prices`.

## Output: REPORT.md and CSVs

The report from either path is the deliverable. Sections, in order: methodology, headline metrics vs SPY (gross), slippage-adjusted scenario (25 bps round-trip on rebalanced fraction), calendar-year returns, growth-of-$1, top-5 drawdowns, year-end concentration profile, turnover, failure summary, limitations, reproducibility.

Companion CSVs: `daily_returns.csv`, `cumulative.csv`, `holdings_top20_<year>.csv` (one per year), `turnover.csv`, `failures.csv`.

Format helpers in [lib/report.py](lib/report.py): `_fmt_pct()` adds a +/- sign (use for spreads/diffs); `_fmt_pct_abs()` is unsigned (use for absolute weights and turnover).

## Known data-quality concerns

These are real, not theoretical. They're disclaimed in each report's "Limitations" section but you should know them when interpreting results:

- **Survivorship bias (EDGAR path).** Inverse-weighted strategies are *especially* exposed: the smallest names get the largest weights, and the smallest names are the most likely to delist. yfinance has gaps for delisted tickers; we drop them, which biases returns upward. The WRDS path mitigates this since CRSP retains delisted history with `dlret`. ~14% of ticker-rebalance pairs were dropped in EDGAR vs ~0.5% in WRDS.
- **Multi-class share weights (EDGAR path).** EDGAR's cover-page CSO concept reports per-class for dual-class issuers (GOOGL/GOOG, BRK.A/BRK.B). The fallback chain in [lib/shares.py](lib/shares.py) handles most cases but the IVV diagnostic showed remaining cases where EDGAR top inverse weights are 6× too high. The cumulative return result is still close to WRDS (the errors cancelled rather than systematically biasing).
- **~45-90 day fundamentals lag (EDGAR path).** SEC requires 10-Q within 40 days; cover-page CSO at our 2024-09-30 rebalance is typically the figure from the Q2 10-Q filed ~2024-07-25. Realistic, but means MC is moderately stale at each rebal.
- **Total CSO, not float-adjusted.** S&P 500 itself uses free-float MC; we use total shares-outstanding. Slight overstatement for names with concentrated insider holdings.
- **fja05680 is community-maintained**, not S&P-licensed. Spot-check known additions/deletions if precision matters.
- **CRSP's `dlret` is sparsely populated.** Many delistings (cash takeouts, some bankruptcies) have null `dlret`. We could improve by inferring from `dlamt`/`dlprc`/`dlretx` — currently we don't.

## When extending

- New metric → [lib/metrics.py](lib/metrics.py), then thread through [lib/report.py](lib/report.py).
- New rebalance cadence (e.g., monthly) → adjust `rebalance_dates()` and the orchestrator's T0 prepend logic.
- Different weighting (capped 1/MC, rank-based, etc.) → modify [lib/weights.py](lib/weights.py) `compute_weights()` and/or [lib/wrds_backtest.py](lib/wrds_backtest.py) `compute_inverse_weights()`. The weighting formula is one line; everything downstream just consumes the `weight` column.
- Pre-2019 IVV holdings parsing → [lib/etf_weights.py](lib/etf_weights.py) currently parses N-Q (which has full 500 holdings) but N-CSR/N-CSRS use a summarized schedule. Extending requires either fetching from another source for the 3/31 and 9/30 quarters or parsing the summary differently.
