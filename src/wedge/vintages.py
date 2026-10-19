"""Raw vintage files: every pull is saved as a timestamped CSV that the database is rebuilt from.

We write our own normalized rows, never EIA's response body, and refuse to write anything
containing the API key, because these files are committed to a public repository.
"""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from wedge import config
from wedge.ingest.types import ROW_COLUMNS, Pull

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


class SecretLeakError(RuntimeError):
    """A vintage file would have contained the API key."""


def vintage_path(pull: Pull, raw_dir: Path = config.RAW_DIR) -> Path:
    stamp = pull.fetched_at.strftime(STAMP_FORMAT)
    return raw_dir / "eia" / f"{pull.fetched_at:%Y}" / f"{stamp}_{pull.source}.csv"


def write_vintage(pull: Pull, raw_dir: Path = config.RAW_DIR) -> Path:
    text = pull.rows[ROW_COLUMNS].to_csv(index=False, lineterminator="\n")
    key = os.environ.get("EIA_API_KEY", "").strip()
    if key and key in text:
        raise SecretLeakError("refusing to write a vintage file containing the API key")
    path = vintage_path(pull, raw_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def read_vintage(path: Path) -> Pull:
    stamp, source = path.stem.split("_", 1)
    rows = pd.read_csv(path, dtype={"series_id": str, "value": float})
    rows["period"] = pd.to_datetime(rows["period"]).dt.date
    return Pull(source=source, fetched_at=datetime.strptime(stamp, STAMP_FORMAT), rows=rows)


def iter_vintages(raw_dir: Path = config.RAW_DIR) -> list[Path]:
    """All vintage files in fetch order (file names sort chronologically)."""
    return sorted((raw_dir / "eia").glob("*/*.csv"), key=lambda p: p.name)
