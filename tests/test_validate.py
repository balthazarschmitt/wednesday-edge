from datetime import date, datetime

import pandas as pd
import pytest

from wedge.ingest.types import Pull
from wedge.validate import ValidationError, check_pull, validate_pull


def test_clean_pull_passes(pull_factory):
    pull = pull_factory({"WCESTUS1": [424410, 428815, 428910]})
    report = validate_pull(pull, ["WCESTUS1"], check_staleness=False)
    assert report.errors == [] and report.warnings == []


def test_missing_series_is_an_error(pull_factory):
    pull = pull_factory({"WCESTUS1": [424410]})
    with pytest.raises(ValidationError, match="missing series"):
        validate_pull(pull, ["WCESTUS1", "WCRFPUS2"], check_staleness=False)


def test_non_friday_duplicate_and_negative_are_errors():
    rows = pd.DataFrame(
        {
            "series_id": ["WCESTUS1"] * 3,
            "period": [date(2026, 10, 8), date(2026, 10, 9), date(2026, 10, 9)],
            "value": [1.0, -5.0, 2.0],
        }
    )
    report = check_pull(Pull("eia_api", datetime(2026, 10, 19), rows), ["WCESTUS1"])
    text = " | ".join(report.errors)
    assert "duplicate" in text and "not Fridays" in text and "negative" in text


def test_utilization_above_105_is_an_error(pull_factory):
    pull = pull_factory({"WPULEUS3": [93.5, 140.0]})
    report = check_pull(pull, ["WPULEUS3"], check_staleness=False)
    assert any("utilization" in e for e in report.errors)


def test_implausible_jump_and_staleness_are_warnings(pull_factory):
    pull = pull_factory(
        {"WCESTUS1": [424410, 470000]}, fetched_at=datetime(2026, 12, 1)
    )  # +45.6 mb in a week; latest period long before fetch
    report = validate_pull(pull, ["WCESTUS1"])
    assert report.errors == []
    assert any("over 30 mb" in w for w in report.warnings)
    assert any("stale" in w for w in report.warnings)
