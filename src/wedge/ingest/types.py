"""Shared ingest types."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

ROW_COLUMNS = ["series_id", "period", "value"]


@dataclass(frozen=True)
class Pull:
    """One fetch from one source. `rows` has columns series_id, period (date), value (float)."""

    source: str
    fetched_at: datetime  # naive UTC
    rows: pd.DataFrame


def utc_now() -> datetime:
    """Current time as naive UTC, the convention used throughout the store."""
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def normalize_rows(records: list[dict]) -> pd.DataFrame:
    """Coerce raw records into the canonical row frame, dropping missing values."""
    df = pd.DataFrame(records, columns=ROW_COLUMNS)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["period"] = pd.to_datetime(df["period"]).dt.date
    df = df.dropna(subset=["value"])
    return df.sort_values(["series_id", "period"]).reset_index(drop=True)
