"""EIA API v2 client: one batched, paginated request per pull, with retry and backoff."""

import logging
import time
from collections.abc import Callable, Iterable
from datetime import date

import httpx

from wedge import config
from wedge.ingest.types import Pull, normalize_rows, utc_now

log = logging.getLogger(__name__)
# httpx logs full request URLs at INFO, and EIA requires the key in the URL.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

PAGE_SIZE = 5000  # EIA's hard cap on rows per response
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class EIAError(RuntimeError):
    """An EIA request failed. Messages never contain the API key."""


def fetch_weekly(
    series_ids: Iterable[str],
    start: date | None = None,
    *,
    client: httpx.Client | None = None,
    api_key: str | None = None,
    max_attempts: int = 5,
    backoff_base_s: float = 3.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Pull:
    """Fetch weekly values for all series in one batched request, following pagination."""
    series_ids = list(series_ids)
    key = api_key or config.eia_api_key()
    url = f"{config.EIA_API_BASE}/{config.EIA_WEEKLY_ROUTE}/data/"
    own_client = client is None
    client = client or httpx.Client(timeout=config.HTTP_TIMEOUT_S)
    records: list[dict] = []
    try:
        offset = 0
        while True:
            params = _params(key, series_ids, start, offset)
            payload = _get_json(client, url, params, key, max_attempts, backoff_base_s, sleep)
            try:
                body = payload["response"]
                page = body["data"]
                total = int(body.get("total", len(page)))
            except (KeyError, TypeError, ValueError) as exc:
                raise EIAError(f"unexpected response shape: {exc!r}") from None
            records += [
                {"series_id": r.get("series"), "period": r.get("period"), "value": r.get("value")}
                for r in page
            ]
            offset += len(page)
            if not page or offset >= total:
                break
    finally:
        if own_client:
            client.close()
    # Offset paging is only safe with a total order; check nothing was skipped or repeated.
    keys = {(r["series_id"], r["period"]) for r in records}
    if len(records) != total or len(keys) != len(records):
        raise EIAError(
            f"inconsistent pagination: {len(records)} rows, {len(keys)} unique, total {total}"
        )
    return Pull(source="eia_api", fetched_at=utc_now(), rows=normalize_rows(records))


def _params(key: str, series_ids: list[str], start: date | None, offset: int) -> list[tuple]:
    params = [
        ("api_key", key),
        ("frequency", "weekly"),
        ("data[0]", "value"),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"),
        # Tiebreaker: without it, rows sharing a period can repeat or vanish across pages.
        ("sort[1][column]", "series"),
        ("sort[1][direction]", "asc"),
        ("offset", str(offset)),
        ("length", str(PAGE_SIZE)),
    ]
    params += [("facets[series][]", sid) for sid in series_ids]
    if start is not None:
        params.append(("start", start.isoformat()))
    return params


def _get_json(client, url, params, key, max_attempts, backoff_base_s, sleep) -> dict:
    last_error = "no attempts made"
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(url, params=params)
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
            elif response.status_code >= 400:
                raise EIAError(f"HTTP {response.status_code} (not retryable; check the API key)")
            else:
                try:
                    return response.json()
                except ValueError:
                    last_error = "response was not JSON"
        except httpx.TransportError as exc:
            # httpx messages can embed the request URL, which carries the key.
            last_error = type(exc).__name__
        log.warning("EIA attempt %d/%d failed: %s", attempt, max_attempts, _redact(last_error, key))
        if attempt < max_attempts:
            sleep(backoff_base_s * 2 ** (attempt - 1))
    raise EIAError(f"all {max_attempts} attempts failed; last error: {_redact(last_error, key)}")


def _redact(text: str, key: str) -> str:
    return text.replace(key, "<redacted>") if key else text
