"""Command-line entry point: `uv run wedge <command>`."""

import logging

import typer

from wedge import __version__, config

app = typer.Typer(
    help="Wednesday Edge: EIA weekly crude inventory forecaster.", no_args_is_help=True
)


@app.callback()
def main() -> None:
    """Keep `wedge` a command group, and load a local .env if present."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config.load_dotenv()


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def ingest(
    full: bool = typer.Option(False, "--full", help="Pull full history instead of recent weeks."),
    source: str = typer.Option("auto", help="auto (API, then XLS fallback), api, or xls."),
) -> None:
    """Pull EIA weekly data, validate it, save a vintage file, and update the database."""
    from wedge.ingest import IngestError
    from wedge.pipeline import ingest as run_ingest
    from wedge.validate import ValidationError

    try:
        result = run_ingest(full=full, source=source)
    except (IngestError, ValidationError) as exc:
        typer.secho(f"Ingest failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None
    rows = result.pull.rows
    typer.echo(
        f"source={result.pull.source} rows={len(rows)} latest={rows['period'].max()} "
        f"inserted={result.inserted} vintage={result.vintage.relative_to(config.REPO_ROOT)}"
    )
    for warning in result.warnings:
        typer.secho(f"warning: {warning}", fg=typer.colors.YELLOW)


@app.command("rebuild-db")
def rebuild_db() -> None:
    """Recreate the local database from the committed vintage files."""
    from wedge.pipeline import rebuild_db as run_rebuild

    typer.echo(f"Replayed {run_rebuild()} vintage files into {config.DB_PATH.name}")


@app.command()
def backtest(
    start: int = typer.Option(2015, help="First test year."),
    end: int = typer.Option(2025, help="Last test year."),
    models: str = typer.Option("all", help="Model set: baselines, candidates, or all."),
) -> None:
    """Walk-forward backtest; writes reports/backtest/<models>.md and predictions CSV."""
    from datetime import date

    from wedge import backtest as bt
    from wedge import features, store

    if models not in bt.MODEL_SETS:
        raise typer.BadParameter(f"unknown model set {models!r}; choose {list(bt.MODEL_SETS)}")
    con = store.connect()
    try:
        wide = features.load_wide(con, vintage="latest")
    finally:
        con.close()
    first, last = date(start, 1, 1), date(end, 12, 31)
    result = bt.run(wide, first, last, bt.MODEL_SETS[models])
    extra = ""
    if models == "all":
        from wedge import selection

        chosen = selection.select(result)
        cols = ["mae", "coverage_80", "brier", "beats_bar", "calibrated", "brier_ok"]
        table = bt._fmt(chosen.table[cols]).to_markdown()
        extra = f"## Model selection (ADR 0005)\n\n{chosen.explain()}\n\n{table}"
        color = typer.colors.GREEN if chosen.passed else typer.colors.YELLOW
        typer.secho(chosen.explain(), fg=color)
    title = f"Backtest: {models}, {start}-{end}"
    path = bt.write_report(result, models, first, last, title, extra)
    typer.echo(bt._fmt(result.summary()).to_string())
    typer.echo(f"Report: {path.relative_to(config.REPO_ROOT)}")


@app.command()
def status() -> None:
    """Show per-series coverage in the local database."""
    from wedge import store

    con = store.connect()
    try:
        df = store.status(con)
    finally:
        con.close()
    df.insert(0, "name", df["series_id"].map(config.SERIES_NAMES))
    typer.echo(df.to_string(index=False) if not df.empty else "Database is empty.")


if __name__ == "__main__":
    app()
