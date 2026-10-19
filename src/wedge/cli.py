"""Command-line entry point: `uv run wedge <command>`."""

import typer

from wedge import __version__

app = typer.Typer(
    help="Wednesday Edge: EIA weekly crude inventory forecaster.", no_args_is_help=True
)


@app.callback()
def main() -> None:
    """Keep `wedge` a command group even while it has a single subcommand."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
