"""EIA Weekly Petroleum Status Report release calendar, deadlines, and decision times.

Rule (pm/adr/0002-data-spike.md): data for the week ending Friday F is released the following
Wednesday at 10:30 ET, unless a federal holiday falls Monday-Wednesday of that week, in which
case it moves to Thursday at 12:00 ET. The rule reproduces every 2026 exception EIA published.
When the rule is wrong it tends to err late, so the deadline guard also checks whether the
actual number is already out before committing a forecast.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

NORMAL_RELEASE = time(10, 30)
HOLIDAY_RELEASE = time(12, 0)
DEADLINE_MARGIN = timedelta(minutes=15)
# Backtests simulate the forecast at Tuesday 18:00 ET, after the API's 16:30 print.
DECISION_TIME = time(18, 0)
FRIDAY = 4

# Published by EIA (eia.gov/petroleum/supply/weekly/schedule.php), retrieved 2026-10-19.
PUBLISHED_2026 = {
    date(2026, 1, 16): datetime(2026, 1, 22, 12, 0, tzinfo=ET),
    date(2026, 2, 13): datetime(2026, 2, 19, 12, 0, tzinfo=ET),
    date(2026, 5, 22): datetime(2026, 5, 28, 12, 0, tzinfo=ET),
    date(2026, 9, 4): datetime(2026, 9, 10, 12, 0, tzinfo=ET),
    date(2026, 10, 9): datetime(2026, 10, 15, 12, 0, tzinfo=ET),
    date(2026, 11, 6): datetime(2026, 11, 12, 12, 0, tzinfo=ET),
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + month // 12, month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    """Federal rule: Saturday holidays are observed Friday, Sunday holidays Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def federal_holidays(year: int) -> set[date]:
    """Observed U.S. federal holidays that fall in `year` (Juneteenth from 2021)."""
    out = set()
    for y in (year, year + 1):  # Jan 1 of next year can be observed on Dec 31
        fixed = [date(y, 1, 1), date(y, 7, 4), date(y, 11, 11), date(y, 12, 25)]
        if y >= 2021:
            fixed.append(date(y, 6, 19))
        out |= {_observed(d) for d in fixed}
        out |= {
            _nth_weekday(y, 1, 0, 3),  # Martin Luther King Jr. Day
            _nth_weekday(y, 2, 0, 3),  # Presidents' Day
            _last_weekday(y, 5, 0),  # Memorial Day
            _nth_weekday(y, 9, 0, 1),  # Labor Day
            _nth_weekday(y, 10, 0, 2),  # Columbus Day
            _nth_weekday(y, 11, 3, 4),  # Thanksgiving
        }
    return {d for d in out if d.year == year}


def is_holiday(d: date) -> bool:
    return d in federal_holidays(d.year)


def _require_friday(period_end: date) -> None:
    if period_end.weekday() != FRIDAY:
        raise ValueError(f"EIA weekly periods end on Fridays; got {period_end:%a %Y-%m-%d}")


def release_time(period_end: date) -> datetime:
    """When EIA publishes data for the week ending `period_end` (timezone-aware, ET)."""
    _require_friday(period_end)
    if period_end in PUBLISHED_2026:
        return PUBLISHED_2026[period_end]
    monday = period_end + timedelta(days=3)
    if any(is_holiday(monday + timedelta(days=i)) for i in range(3)):
        return datetime.combine(monday + timedelta(days=3), HOLIDAY_RELEASE, tzinfo=ET)
    return datetime.combine(monday + timedelta(days=2), NORMAL_RELEASE, tzinfo=ET)


def deadline(period_end: date) -> datetime:
    """Latest time a forecast for `period_end` may be committed."""
    return release_time(period_end) - DEADLINE_MARGIN


class DeadlineMissed(RuntimeError):
    """A forecast was attempted after its deadline; the week must be recorded as missed."""


def check_open(period_end: date, now: datetime) -> None:
    """Deadline guard: raise unless a forecast for `period_end` may still be committed at `now`."""
    if now.tzinfo is None:
        raise ValueError("expected a timezone-aware datetime")
    if now >= deadline(period_end):
        raise DeadlineMissed(
            f"forecast for week ending {period_end} closed at "
            f"{deadline(period_end):%a %Y-%m-%d %H:%M %Z}"
        )


def decision_time(period_end: date) -> datetime:
    """The simulated forecast time used in backtests: Tuesday 18:00 ET after the period."""
    _require_friday(period_end)
    return datetime.combine(period_end + timedelta(days=4), DECISION_TIME, tzinfo=ET)


def last_friday_on_or_before(d: date) -> date:
    return d - timedelta(days=(d.weekday() - FRIDAY) % 7)


def target_period(now: datetime) -> date:
    """The earliest week whose data is not yet released at `now`: the week to forecast."""
    friday = last_friday_on_or_before(now.astimezone(ET).date()) - timedelta(weeks=1)
    while release_time(friday) <= now:
        friday += timedelta(weeks=1)
    return friday


def to_utc_naive(dt: datetime) -> datetime:
    """Convert an aware datetime to the naive-UTC convention used by the store."""
    if dt.tzinfo is None:
        raise ValueError("expected a timezone-aware datetime")
    return dt.astimezone(UTC).replace(tzinfo=None)
