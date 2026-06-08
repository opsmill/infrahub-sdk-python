import typer
from rich.console import Console
from typer.testing import CliRunner

from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl.utils import catch_exception
from tests.helpers.cli import remove_ansi_color

runner = CliRunner()


def test_catch_exception_async_passes_through_typer_exit() -> None:
    console = Console()
    app = AsyncTyper()

    @app.command()
    @catch_exception(console=console)
    async def fail() -> None:
        console.print("human-readable failure message")
        raise typer.Exit(1)

    result = runner.invoke(app, [])
    stdout = remove_ansi_color(result.stdout)

    assert result.exit_code == 1
    assert "human-readable failure message" in stdout
    assert "Traceback" not in stdout
    assert "Error: 1" not in stdout


def test_catch_exception_sync_passes_through_typer_exit() -> None:
    console = Console()
    app = typer.Typer()

    @app.command()
    @catch_exception(console=console)
    def fail() -> None:
        console.print("human-readable failure message")
        raise typer.Exit(1)

    result = runner.invoke(app, [])
    stdout = remove_ansi_color(result.stdout)

    assert result.exit_code == 1
    assert "human-readable failure message" in stdout
    assert "Traceback" not in stdout
    assert "Error: 1" not in stdout
