from datetime import date, datetime

import pytest

from wedge import pipeline, store, vintages

T1 = datetime(2026, 10, 14, 15, 0, 0)
T2 = datetime(2026, 10, 21, 15, 0, 0)


@pytest.fixture
def con():
    c = store.connect(":memory:")
    yield c
    c.close()


def test_overlapping_identical_pull_inserts_nothing(con, pull_factory):
    assert store.write_pull(con, pull_factory({"A": [1, 2, 3]}, fetched_at=T1)) == 3
    assert store.write_pull(con, pull_factory({"A": [1, 2, 3]}, fetched_at=T2)) == 0


def test_revision_is_kept_with_its_fetch_time(con, pull_factory):
    store.write_pull(con, pull_factory({"A": [1, 2, 3]}, fetched_at=T1))
    assert store.write_pull(con, pull_factory({"A": [1, 2, 99]}, fetched_at=T2)) == 1

    latest = store.latest(con)
    assert latest["value"].tolist() == [1, 2, 99]

    before = store.known_as_of(con, datetime(2026, 10, 20))
    assert before["value"].tolist() == [1, 2, 3]
    assert store.status(con)["revisions"].tolist() == [1]


def test_vintage_round_trip(tmp_path, pull_factory):
    pull = pull_factory({"WCESTUS1": [424134, 415577]}, fetched_at=T1)
    path = vintages.write_vintage(pull, tmp_path)
    assert path.name == "20261014T150000Z_eia_api.csv"
    back = vintages.read_vintage(path)
    assert back.fetched_at == T1 and back.source == "eia_api"
    assert back.rows["period"].tolist() == [date(2026, 8, 7), date(2026, 8, 14)]
    assert back.rows["value"].tolist() == [424134.0, 415577.0]


def test_vintage_refuses_to_write_the_api_key(tmp_path, pull_factory, monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "LEAKY_KEY_123456")
    pull = pull_factory({"LEAKY_KEY_123456": [1.0]})
    with pytest.raises(vintages.SecretLeakError):
        vintages.write_vintage(pull, tmp_path)
    assert not list(tmp_path.rglob("*.csv"))


def test_rebuild_db_reproduces_revision_log(tmp_path, pull_factory):
    raw = tmp_path / "raw"
    vintages.write_vintage(pull_factory({"A": [1, 2, 3]}, fetched_at=T1), raw)
    vintages.write_vintage(pull_factory({"A": [1, 2, 99]}, fetched_at=T2), raw)

    db = tmp_path / "wedge.duckdb"
    assert pipeline.rebuild_db(db, raw) == 2
    c = store.connect(db)
    try:
        assert store.latest(c)["value"].tolist() == [1, 2, 99]
        assert store.known_as_of(c, T1)["value"].tolist() == [1, 2, 3]
    finally:
        c.close()


def test_ingest_end_to_end_with_fake_source(tmp_path, pull_factory, monkeypatch):
    from wedge import config

    ids = list(config.ALL_SERIES.values())
    fake = pull_factory({sid: [100.0, 101.0] for sid in ids}, fetched_at=T1)
    monkeypatch.setattr(pipeline, "pull_with_fallback", lambda *a, **k: fake)

    result = pipeline.ingest(
        today=date(2026, 8, 20), db_path=tmp_path / "w.duckdb", raw_dir=tmp_path / "raw"
    )
    assert result.inserted == 2 * len(ids)
    assert result.vintage.exists()
