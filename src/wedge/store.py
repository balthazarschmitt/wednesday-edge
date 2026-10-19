"""DuckDB store. `observations` is a revision log: one row per (series, period) per distinct value.

A value is only inserted when it differs from the latest stored value for that series and
period, so routine overlapping pulls add nothing and genuine EIA revisions are preserved with
the time we first saw them. All timestamps are naive UTC.
"""

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from wedge import config
from wedge.ingest.types import Pull

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    series_id  VARCHAR   NOT NULL,
    period     DATE      NOT NULL,
    value      DOUBLE    NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    source     VARCHAR   NOT NULL,
    PRIMARY KEY (series_id, period, fetched_at)
);
"""

LATEST_VALUES = """
SELECT series_id, period, value, fetched_at, source FROM observations
QUALIFY row_number() OVER (PARTITION BY series_id, period ORDER BY fetched_at DESC) = 1
"""


def connect(path: Path | str = config.DB_PATH) -> duckdb.DuckDBPyConnection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(SCHEMA)
    return con


def write_pull(con: duckdb.DuckDBPyConnection, pull: Pull) -> int:
    """Insert rows that are new or revised; return how many were inserted."""
    incoming = pull.rows[["series_id", "period", "value"]].copy()
    incoming["fetched_at"] = pull.fetched_at
    incoming["source"] = pull.source
    con.register("incoming", incoming)
    try:
        new = con.execute(
            f"""
            SELECT i.* FROM incoming i
            LEFT JOIN ({LATEST_VALUES}) cur USING (series_id, period)
            WHERE cur.value IS NULL OR cur.value <> i.value
            """
        ).df()
        if not new.empty:
            con.register("new_rows", new)
            con.execute(
                "INSERT INTO observations "
                "SELECT series_id, period, value, fetched_at, source FROM new_rows"
            )
            con.unregister("new_rows")
    finally:
        con.unregister("incoming")
    return len(new)


def latest(con: duckdb.DuckDBPyConnection, series_ids: list[str] | None = None) -> pd.DataFrame:
    """Latest known value for every (series, period), long format."""
    df = con.execute(f"SELECT * FROM ({LATEST_VALUES}) ORDER BY series_id, period").df()
    if series_ids is not None:
        df = df[df["series_id"].isin(series_ids)]
    df["period"] = pd.to_datetime(df["period"]).dt.date
    return df.reset_index(drop=True)


def known_as_of(con: duckdb.DuckDBPyConnection, fetched_by: datetime) -> pd.DataFrame:
    """The value we held for each (series, period) using only pulls made by `fetched_by`."""
    df = con.execute(
        """
        SELECT series_id, period, value, fetched_at FROM observations
        WHERE fetched_at <= ?
        QUALIFY row_number() OVER (PARTITION BY series_id, period ORDER BY fetched_at DESC) = 1
        ORDER BY series_id, period
        """,
        [fetched_by],
    ).df()
    df["period"] = pd.to_datetime(df["period"]).dt.date
    return df


def status(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Per-series coverage summary."""
    return con.execute(
        """
        SELECT series_id, min(period) AS first_period, max(period) AS last_period,
               count(DISTINCT period) AS periods, max(fetched_at) AS last_fetch,
               count(*) - count(DISTINCT period) AS revisions
        FROM observations GROUP BY series_id ORDER BY series_id
        """
    ).df()
