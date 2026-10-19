"""Fallback source: EIA's legacy per-series XLS workbooks (no API key needed)."""

import io
from collections.abc import Iterable
from datetime import date

import httpx
import pandas as pd

from wedge import config
from wedge.ingest.eia import EIAError
from wedge.ingest.types import Pull, normalize_rows, utc_now

DATA_SHEET = "Data 1"
HEADER_ROWS = 3  # "Back to Contents", "Sourcekey", "Date"


def fetch_weekly_xls(
    series_ids: Iterable[str], start: date | None = None, *, client: httpx.Client | None = None
) -> Pull:
    """Download each series' workbook and return the same row frame as the API client."""
    own_client = client is None
    client = client or httpx.Client(timeout=config.HTTP_TIMEOUT_S, follow_redirects=True)
    frames = []
    try:
        for sid in series_ids:
            try:
                response = client.get(config.EIA_XLS_URL.format(series_id=sid))
                response.raise_for_status()
                sheet = pd.read_excel(io.BytesIO(response.content), DATA_SHEET, header=None)
            except (httpx.HTTPError, ValueError) as exc:
                raise EIAError(f"XLS for {sid} failed: {type(exc).__name__}") from None
            frames.append(parse_sheet(sheet, sid))
    finally:
        if own_client:
            client.close()
    rows = pd.concat(frames, ignore_index=True) if frames else normalize_rows([])
    if start is not None:
        rows = rows[rows["period"] >= start].reset_index(drop=True)
    return Pull(source="eia_xls", fetched_at=utc_now(), rows=rows)


def parse_sheet(sheet: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """Parse a raw `Data 1` sheet (read with header=None), checking it is the expected series."""
    if sheet.shape[0] <= HEADER_ROWS or sheet.shape[1] < 2:
        raise EIAError(f"XLS for {series_id} has an unexpected shape {sheet.shape}")
    source_key = str(sheet.iat[1, 1]).strip()
    if source_key != series_id:
        raise EIAError(f"XLS sourcekey {source_key!r} does not match {series_id!r}")
    body = sheet.iloc[HEADER_ROWS:, :2]
    records = [
        {"series_id": series_id, "period": period, "value": value}
        for period, value in body.itertuples(index=False)
    ]
    return normalize_rows(records)
