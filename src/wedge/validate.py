"""Sanity checks run on every pull before anything is stored."""

from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd

from wedge import config
from wedge.ingest.types import Pull

# The largest weekly commercial crude moves on record are around ±20 mb; beyond this, flag it.
MAX_PLAUSIBLE_WEEKLY_MOVE_KB = 30_000
# Normal lag from period end to fetch is 5-6 days; holiday weeks add one.
STALE_AFTER = timedelta(days=13)
UTILIZATION_SERIES = config.FLOW_SERIES["refinery_utilization"]


class ValidationError(ValueError):
    """A pull failed a hard check and must not be stored."""


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_pull(pull: Pull, expected_series: list[str], *, check_staleness: bool = True) -> Report:
    """Return hard errors and soft warnings for a pull."""
    report = Report()
    rows = pull.rows
    missing = sorted(set(expected_series) - set(rows["series_id"]))
    if missing:
        report.errors.append(f"missing series: {missing}")
    if rows.empty:
        report.errors.append("pull returned no rows")
        return report

    dupes = rows.duplicated(["series_id", "period"]).sum()
    if dupes:
        report.errors.append(f"{dupes} duplicate (series, period) rows")
    non_friday = rows[pd.to_datetime(rows["period"]).dt.weekday != 4]
    if not non_friday.empty:
        report.errors.append(f"{len(non_friday)} periods are not Fridays")
    negative = rows[rows["value"] < 0]
    if not negative.empty:
        report.errors.append(f"{len(negative)} negative values")
    util = rows[(rows["series_id"] == UTILIZATION_SERIES) & (rows["value"] > 105)]
    if not util.empty:
        report.errors.append(f"{len(util)} refinery utilization values above 105%")

    for sid in config.STOCK_SERIES.values():
        series = rows[rows["series_id"] == sid].sort_values("period")
        jumps = series["value"].diff().abs() > MAX_PLAUSIBLE_WEEKLY_MOVE_KB
        if jumps.any():
            report.warnings.append(f"{sid}: {int(jumps.sum())} weekly moves over 30 mb")

    if check_staleness:
        latest = max(rows["period"])
        if pull.fetched_at.date() - latest > STALE_AFTER:
            report.warnings.append(f"latest period {latest} is stale at fetch {pull.fetched_at}")
    return report


def validate_pull(pull: Pull, expected_series: list[str], **kwargs) -> Report:
    """Raise ValidationError on hard failures; return the report (with warnings) otherwise."""
    report = check_pull(pull, expected_series, **kwargs)
    if report.errors:
        raise ValidationError("; ".join(report.errors))
    return report
