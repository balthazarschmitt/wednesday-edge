"""Ingest orchestration: pull → validate → save vintage → store."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from wedge import config, store, vintages
from wedge.ingest import Pull, pull_with_fallback
from wedge.validate import validate_pull

log = logging.getLogger(__name__)

# Incremental pulls re-read recent weeks so late EIA revisions are captured.
INCREMENTAL_LOOKBACK = timedelta(weeks=10)


@dataclass
class IngestResult:
    pull: Pull
    vintage: Path
    inserted: int
    warnings: list[str]


def ingest(
    *,
    full: bool = False,
    source: str = "auto",
    today: date | None = None,
    db_path: Path | str = config.DB_PATH,
    raw_dir: Path = config.RAW_DIR,
) -> IngestResult:
    series_ids = list(config.ALL_SERIES.values())
    start = None if full else (today or date.today()) - INCREMENTAL_LOOKBACK
    pull = pull_with_fallback(series_ids, start, source=source)
    report = validate_pull(pull, series_ids)
    for warning in report.warnings:
        log.warning(warning)
    path = vintages.write_vintage(pull, raw_dir)
    con = store.connect(db_path)
    try:
        inserted = store.write_pull(con, pull)
    finally:
        con.close()
    return IngestResult(pull=pull, vintage=path, inserted=inserted, warnings=report.warnings)


def rebuild_db(db_path: Path = config.DB_PATH, raw_dir: Path = config.RAW_DIR) -> int:
    """Recreate the database from vintage files alone; return the number of vintages replayed."""
    db_path = Path(db_path)
    for suffix in ("", ".wal"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    con = store.connect(db_path)
    try:
        paths = vintages.iter_vintages(raw_dir)
        for path in paths:
            store.write_pull(con, vintages.read_vintage(path))
    finally:
        con.close()
    return len(paths)
