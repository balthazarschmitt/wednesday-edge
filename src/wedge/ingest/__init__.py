"""Data ingest: the EIA API first, then the legacy XLS workbooks as a fallback."""

import logging
from collections.abc import Iterable
from datetime import date

from wedge.ingest.eia import EIAError, fetch_weekly
from wedge.ingest.eia_xls import fetch_weekly_xls
from wedge.ingest.types import Pull

log = logging.getLogger(__name__)

__all__ = ["EIAError", "IngestError", "Pull", "pull_with_fallback"]


class IngestError(RuntimeError):
    """Every source failed; callers fall back to the last stored vintage."""


def pull_with_fallback(
    series_ids: Iterable[str], start: date | None = None, *, source: str = "auto"
) -> Pull:
    """Pull weekly series from the API, falling back to XLS when the API fails."""
    series_ids = list(series_ids)
    errors = []
    if source in ("auto", "api"):
        try:
            return fetch_weekly(series_ids, start)
        except EIAError as exc:
            log.warning("EIA API failed, trying XLS fallback: %s", exc)
            errors.append(f"api: {exc}")
    if source in ("auto", "xls"):
        try:
            return fetch_weekly_xls(series_ids, start)
        except EIAError as exc:
            log.warning("EIA XLS fallback failed: %s", exc)
            errors.append(f"xls: {exc}")
    raise IngestError("; ".join(errors) or f"unknown source {source!r}")
