import logging
from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest

from wedge.ingest import eia
from wedge.ingest.eia import EIAError, fetch_weekly

KEY = "FAKEKEY1234567890abcdefghij"


def row(sid, period, value):
    return {"series": sid, "period": period, "value": value}


def page(rows, total):
    return {"response": {"total": str(total), "data": rows}}


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_batches_all_series_in_one_request_with_start():
    seen = []

    def handler(request):
        seen.append(parse_qs(request.url.query.decode()))
        return httpx.Response(200, json=page([row("A", "2026-10-09", "1.5")], 1))

    fetch_weekly(["A", "B"], date(2026, 9, 1), client=client_for(handler), api_key=KEY)
    assert len(seen) == 1
    assert seen[0]["facets[series][]"] == ["A", "B"]
    assert seen[0]["start"] == ["2026-09-01"]


def test_follows_pagination(monkeypatch):
    monkeypatch.setattr(eia, "PAGE_SIZE", 2)
    all_rows = [row("A", f"2026-0{m}-07", m) for m in range(1, 6)]

    def handler(request):
        offset = int(parse_qs(request.url.query.decode())["offset"][0])
        return httpx.Response(200, json=page(all_rows[offset : offset + 2], len(all_rows)))

    pull = fetch_weekly(["A"], client=client_for(handler), api_key=KEY)
    assert len(pull.rows) == 5
    assert pull.source == "eia_api"


def test_retries_transient_failures_with_backoff():
    responses = iter(
        [
            httpx.Response(502, text="<html>Bad Gateway</html>"),
            httpx.ReadTimeout("timed out"),
            httpx.Response(200, text="not json"),
            httpx.Response(200, json=page([row("A", "2026-10-09", "415577")], 1)),
        ]
    )

    def handler(request):
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return item

    sleeps = []
    pull = fetch_weekly(
        ["A"], client=client_for(handler), api_key=KEY, backoff_base_s=1, sleep=sleeps.append
    )
    assert pull.rows["value"].tolist() == [415577.0]
    assert sleeps == [1, 2, 4]


def test_gives_up_after_max_attempts_without_leaking_key():
    def handler(request):
        raise httpx.ConnectError(f"failed to reach {request.url}")

    with pytest.raises(EIAError) as exc:
        fetch_weekly(["A"], client=client_for(handler), api_key=KEY, sleep=lambda s: None)
    assert KEY not in str(exc.value)
    assert "5 attempts" in str(exc.value)


def test_auth_error_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(403, json={"error": "invalid key"})

    with pytest.raises(EIAError, match="not retryable"):
        fetch_weekly(["A"], client=client_for(handler), api_key=KEY, sleep=lambda s: None)
    assert len(calls) == 1


def test_null_values_are_dropped_and_strings_coerced():
    def handler(request):
        rows = [row("A", "2026-10-02", None), row("A", "2026-10-09", "424134")]
        return httpx.Response(200, json=page(rows, 2))

    pull = fetch_weekly(["A"], client=client_for(handler), api_key=KEY)
    assert pull.rows["period"].tolist() == [date(2026, 10, 9)]
    assert pull.rows["value"].tolist() == [424134.0]


def test_pages_with_repeated_rows_are_rejected(monkeypatch):
    """Regression: unstable sort made a row repeat across a page boundary (2026-10-19)."""
    monkeypatch.setattr(eia, "PAGE_SIZE", 2)
    pages = {
        0: [row("A", "2026-10-02", 1), row("B", "2026-10-02", 2)],
        2: [row("B", "2026-10-02", 2), row("A", "2026-10-09", 3)],
    }

    def handler(request):
        offset = int(parse_qs(request.url.query.decode())["offset"][0])
        return httpx.Response(200, json=page(pages[offset], 4))

    with pytest.raises(EIAError, match="inconsistent pagination"):
        fetch_weekly(["A", "B"], client=client_for(handler), api_key=KEY)


def test_sort_has_series_tiebreaker():
    seen = []

    def handler(request):
        seen.append(parse_qs(request.url.query.decode()))
        return httpx.Response(200, json=page([], 0))

    fetch_weekly(["A"], client=client_for(handler), api_key=KEY)
    assert seen[0]["sort[1][column]"] == ["series"]


def test_api_key_never_appears_in_logs(caplog):
    """Regression: httpx logged full request URLs, key included, at INFO (2026-10-19)."""
    caplog.set_level(logging.DEBUG)

    def handler(request):
        return httpx.Response(200, json=page([row("A", "2026-10-09", 1)], 1))

    fetch_weekly(["A"], client=client_for(handler), api_key=KEY)
    assert KEY not in caplog.text


def test_unexpected_shape_raises():
    def handler(request):
        return httpx.Response(200, json={"error": "something"})

    with pytest.raises(EIAError, match="unexpected response shape"):
        fetch_weekly(["A"], client=client_for(handler), api_key=KEY)
