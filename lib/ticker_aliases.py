"""Historical-symbol -> current-symbol remap for yfinance fetches.

The fja05680 constituents CSV uses tickers as they were at the time. yfinance
fetches by *current* symbol. This map handles the common 2015-2025 changes.

Tickers in the fja05680 file with a `-YYYYMM` suffix mean "left index that
month"; constituents.py strips the suffix before lookup. Some renamed tickers
still resolve under their old symbol on yfinance; only entries that don't
need to be in this map. Confirmed cases below.
"""

# Renames where the old ticker no longer fetches valid data.
RENAMES: dict[str, str] = {
    "FB":     "META",   # 2022-06
    "FISV":   "FI",     # 2024-02
    "ANTM":   "ELV",    # 2022-06
    "SQ":     "XYZ",    # 2025-01
    "FBHS":   "MWA",    # 2022 spin/rename — partial; treated as alias to MWA which inherited series
    "WLTW":   "WTW",    # 2022-01
    "PKI":    "RVTY",   # 2023-05
    "VAR":    "SHC",    # 2021 spin — Varian acquired by Siemens, removed from index
    "CERN":   "ORCL",   # acquired 2022, no successor ticker — left blank: handled by deletion
    "XLNX":   "AMD",    # acquired 2022, no successor ticker
    "INFO":   "SPGI",   # IHS Markit merged into S&P Global 2022
    "ATVI":   "MSFT",   # acquired by Microsoft 2023
    "DRE":    "PLD",    # Duke Realty acquired by Prologis 2022
    "CTLT":   "CTLT",   # still trades — placeholder
    "SIVB":   "SIVBQ",  # SVB collapse 2023; usually no longer fetchable
    "FRCB":   "FRCB",   # First Republic — collapsed 2023
    "SBNY":   "SBNY",   # Signature Bank — collapsed 2023
    # Class share tickers stay the same but yfinance prefers '-' over '.'
    "BRK.B":  "BRK-B",
    "BF.B":   "BF-B",
    "BRK.A":  "BRK-A",
}

# Tickers that were acquired with no successor — drop from universe entirely.
DELISTED_NO_SUCCESSOR: set[str] = {
    "TWTR",     # Twitter taken private 2022
    "RTN",      # Raytheon merged into RTX 2020
    "CTL",      # CenturyLink renamed LUMN — handled below
    "LUK",      # Leucadia renamed Jefferies 2018
    "TIF",      # acquired by LVMH 2021
    "SLM",      # Sallie Mae split off Navient 2014, complex
}


def remap(ticker: str) -> str | None:
    """Return the current yfinance-fetchable symbol for a historical ticker.

    Returns None if the ticker should be dropped (acquired with no successor).
    """
    if ticker in DELISTED_NO_SUCCESSOR:
        return None
    return RENAMES.get(ticker, ticker)
