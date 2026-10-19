from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from wedge.ingest.types import Pull, normalize_rows

FIRST_FRIDAY = date(2026, 8, 7)


def make_pull(values: dict[str, list[float]], *, fetched_at=None, source="eia_api", start=None):
    """Build a Pull with consecutive Friday periods for each series."""
    start = start or FIRST_FRIDAY
    records = [
        {"series_id": sid, "period": start + timedelta(weeks=i), "value": v}
        for sid, vals in values.items()
        for i, v in enumerate(vals)
    ]
    return Pull(
        source=source,
        fetched_at=fetched_at or datetime(2026, 10, 19, 12, 0, 0),
        rows=normalize_rows(records),
    )


@pytest.fixture
def pull_factory():
    return make_pull


@pytest.fixture(autouse=True)
def _no_real_key(monkeypatch):
    """Tests never see a real key (not even from a local .env); tests that need one set a fake."""
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    monkeypatch.setattr("wedge.config.load_dotenv", lambda *a, **k: None)


@pytest.fixture
def empty_frame():
    return pd.DataFrame(columns=["series_id", "period", "value"])
