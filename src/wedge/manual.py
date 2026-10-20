"""The weekly human inputs: API print, analyst consensus, and model overrides.

Values are entered in million barrels, as news reports print them, and stored in thousand
barrels. Every entry needs a source URL. Overrides must be logged before the deadline;
consensus and API prints may be backfilled later, and say so in `logged_before_deadline`.
"""

from datetime import date, datetime
from pathlib import Path

from wedge import ledger, releases


def _url(url: str) -> str:
    if not url.startswith(("https://", "http://")):
        raise ledger.LedgerError("a source URL (http/https) is required")
    return url


def _base(period: date, now: datetime, change_mb: float) -> dict:
    return {
        "target_period": str(period),
        "commodity": ledger.COMMODITY,
        "change_kb": round(change_mb * 1000, 1),
        "logged_at": ledger.iso(now),
        "logged_before_deadline": now < releases.deadline(period),
    }


def log_api(base: Path, change_mb: float, url: str, now: datetime, period: date | None = None):
    period = period or releases.target_period(now)
    path = ledger.api_path(base, period)
    ledger.write_once(path, {**_base(period, now, change_mb), "url": _url(url)})
    return path


def log_consensus(
    base: Path, change_mb: float, source: str, url: str, now: datetime, period: date | None = None
):
    period = period or releases.target_period(now)
    path = ledger.consensus_path(base, period, source)
    entry = {**_base(period, now, change_mb), "source": source, "url": _url(url)}
    ledger.write_once(path, entry)
    return path


def log_override(base: Path, change_mb: float, reason: str, now: datetime):
    period = releases.target_period(now)
    releases.check_open(period, now)  # an override after the deadline is never accepted
    if len(reason.strip()) < 10:
        raise ledger.LedgerError("an override needs a reason of at least 10 characters")
    path = ledger.override_path(base, period)
    ledger.write_once(path, {**_base(period, now, change_mb), "reason": reason.strip()})
    return path
