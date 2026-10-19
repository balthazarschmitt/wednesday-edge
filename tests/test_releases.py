from datetime import date, datetime

import pytest

from wedge import releases
from wedge.releases import ET, deadline, decision_time, release_time, target_period


@pytest.mark.parametrize(("period", "expected"), sorted(releases.PUBLISHED_2026.items()))
def test_rule_reproduces_every_published_2026_exception(period, expected, monkeypatch):
    monkeypatch.setattr(releases, "PUBLISHED_2026", {})  # test the rule, not the table
    assert release_time(period) == expected


def test_normal_week_is_wednesday_1030():
    assert release_time(date(2026, 10, 16)) == datetime(2026, 10, 21, 10, 30, tzinfo=ET)


@pytest.mark.parametrize(
    ("period", "note"),
    [
        (date(2026, 11, 20), "Thanksgiving is a Thursday"),
        (date(2026, 12, 25), "Christmas Friday is the period end, not the release week"),
        (date(2026, 12, 18), "Christmas falls on the Friday after release"),
        (date(2026, 6, 12), "Juneteenth 2026 is a Friday"),
    ],
)
def test_holidays_outside_mon_to_wed_do_not_shift(period, note):
    assert release_time(period).weekday() == 2, note


def test_new_years_on_wednesday_shifts_to_thursday():
    # Jan 1 2025 was a Wednesday; data for the week ending Dec 27 2024 came out Thursday.
    assert release_time(date(2024, 12, 27)) == datetime(2025, 1, 2, 12, 0, tzinfo=ET)


def test_observed_holidays():
    hol = releases.federal_holidays(2027)
    assert date(2027, 7, 5) in hol  # July 4 2027 is a Sunday
    assert date(2026, 12, 31) not in hol
    assert date(2021, 12, 31) in releases.federal_holidays(2021)  # Jan 1 2022 is a Saturday


def test_deadline_is_before_release_and_handles_dst():
    period = date(2026, 10, 30)  # release Wed Nov 4, after the Nov 1 DST change
    assert deadline(period) < release_time(period)
    assert release_time(period).utcoffset().total_seconds() == -5 * 3600
    assert release_time(date(2026, 10, 16)).utcoffset().total_seconds() == -4 * 3600


def test_decision_time_is_tuesday_evening_before_release():
    period = date(2026, 10, 16)
    t = decision_time(period)
    assert t == datetime(2026, 10, 20, 18, 0, tzinfo=ET)
    assert t < deadline(period)


def test_non_friday_rejected():
    with pytest.raises(ValueError, match="Fridays"):
        release_time(date(2026, 10, 15))


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 20, 18, 0, tzinfo=ET), date(2026, 10, 16)),  # Tuesday evening
        (datetime(2026, 10, 21, 10, 29, tzinfo=ET), date(2026, 10, 16)),  # just before release
        (datetime(2026, 10, 21, 10, 30, tzinfo=ET), date(2026, 10, 23)),  # released
        (datetime(2026, 10, 14, 12, 0, tzinfo=ET), date(2026, 10, 9)),  # Columbus Day week
        (datetime(2026, 10, 15, 11, 0, tzinfo=ET), date(2026, 10, 9)),  # Thursday, pre-release
        (datetime(2026, 10, 15, 12, 0, tzinfo=ET), date(2026, 10, 16)),
    ],
)
def test_target_period(now, expected):
    assert target_period(now) == expected


def test_deadline_guard():
    period = date(2026, 10, 9)  # Columbus Day week: release Thu Oct 15 12:00, deadline 11:45
    releases.check_open(period, datetime(2026, 10, 15, 11, 44, tzinfo=ET))
    with pytest.raises(releases.DeadlineMissed):
        releases.check_open(period, datetime(2026, 10, 15, 11, 45, tzinfo=ET))
    with pytest.raises(releases.DeadlineMissed):  # same instant expressed in UTC
        releases.check_open(period, datetime(2026, 10, 15, 15, 45, tzinfo=releases.UTC))
    with pytest.raises(ValueError):
        releases.check_open(period, datetime(2026, 10, 15, 11, 0))


def test_to_utc_naive_requires_aware():
    with pytest.raises(ValueError):
        releases.to_utc_naive(datetime(2026, 10, 20))
