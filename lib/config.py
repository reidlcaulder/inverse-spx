"""Centralized config — env vars with sensible defaults / explicit failures.

All shared secrets and identity info funnel through here so the rest of the
code never hardcodes a personal email or username. Reads `.env` in the repo
root if present.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def sec_user_agent() -> str:
    """User-Agent string for SEC EDGAR requests.

    SEC requires a real contact email per their fair-access policy:
    https://www.sec.gov/os/accessing-edgar-data
    Set SEC_EDGAR_USER_AGENT_EMAIL to your email in .env or environment.
    """
    email = os.environ.get("SEC_EDGAR_USER_AGENT_EMAIL", "").strip()
    if not email:
        raise RuntimeError(
            "Set SEC_EDGAR_USER_AGENT_EMAIL in .env or environment. "
            "SEC requires a contact email in the User-Agent header for EDGAR requests."
        )
    return f"inverse-spx-research {email}"


def wrds_username() -> str | None:
    """WRDS username for `wrds.Connection(wrds_username=...)`.

    Returns None if not configured (in which case the WRDS path is unavailable).
    """
    return os.environ.get("WRDS_USERNAME")
