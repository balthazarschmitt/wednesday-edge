from datetime import date, datetime

import httpx
import pandas as pd
import pytest

from wedge.ingest import IngestError, eia_xls, pull_with_fallback
from wedge.ingest.eia import EIAError
from wedge.ingest.types import Pull


def raw_sheet(source_key="WCESTUS1"):
    """Mimic EIA's `Data 1` sheet as read with header=None."""
    return pd.DataFrame(
        [
            ["Back to Contents", "Data 1: Weekly U.S. Ending Stocks ..."],
            ["Sourcekey", source_key],
            ["Date", "Weekly U.S. Ending Stocks ..."],
            [datetime(2026, 10, 2), 424134],
            [datetime(2026, 10, 9), 415577],
        ]
    )


def test_parse_sheet():
    rows = eia_xls.parse_sheet(raw_sheet(), "WCESTUS1")
    assert rows["period"].tolist() == [date(2026, 10, 2), date(2026, 10, 9)]
    assert rows["value"].tolist() == [424134.0, 415577.0]
    assert set(rows["series_id"]) == {"WCESTUS1"}


def test_parse_sheet_rejects_wrong_series():
    with pytest.raises(EIAError, match="does not match"):
        eia_xls.parse_sheet(raw_sheet("WGTSTUS1"), "WCESTUS1")


def test_xls_http_failure_is_eia_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(EIAError, match="XLS for WCESTUS1 failed"):
        eia_xls.fetch_weekly_xls(["WCESTUS1"], client=client)


def _pull(source):
    return Pull(source, datetime(2026, 10, 19), pd.DataFrame(columns=["series_id", "period"]))


def test_fallback_used_when_api_fails(monkeypatch):
    def api_down(*a, **k):
        raise EIAError("HTTP 502")

    monkeypatch.setattr("wedge.ingest.fetch_weekly", api_down)
    monkeypatch.setattr("wedge.ingest.fetch_weekly_xls", lambda *a, **k: _pull("eia_xls"))
    assert pull_with_fallback(["WCESTUS1"]).source == "eia_xls"


def test_both_sources_failing_raises_ingest_error(monkeypatch):
    def down(*a, **k):
        raise EIAError("down")

    monkeypatch.setattr("wedge.ingest.fetch_weekly", down)
    monkeypatch.setattr("wedge.ingest.fetch_weekly_xls", down)
    with pytest.raises(IngestError, match="api: down; xls: down"):
        pull_with_fallback(["WCESTUS1"])
