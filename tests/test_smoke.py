import pytest

from wedge import config
from wedge.cli import app


def test_cli_version():
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_primary_target_is_configured():
    assert config.PRIMARY_TARGET in config.STOCK_SERIES


def test_missing_api_key_fails_loudly(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="EIA_API_KEY"):
        config.eia_api_key()
