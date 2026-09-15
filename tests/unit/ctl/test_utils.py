from io import StringIO

import typer
from rich.console import Console
from typer.testing import CliRunner

from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl.utils import catch_exception, print_graphql_errors, print_graphql_query_errors
from infrahub_sdk.exceptions import graphql_error_from_response
from tests.helpers.cli import remove_ansi_color

runner = CliRunner()


def rendered(recorder: Console) -> str:
    return remove_ansi_color(recorder.file.getvalue())  # type: ignore[attr-defined]


def recording_console() -> Console:
    """A console that captures its output instead of writing it to the terminal."""
    return Console(record=True, file=StringIO(), width=200)


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


def test_print_graphql_errors_renders_the_server_errors() -> None:
    console = recording_console()

    print_graphql_errors(
        console=console,
        errors=[{"message": "boom", "path": ["TestPerson"]}],
        fallback="never reached",
    )

    output = rendered(console)
    assert "boom" in output
    assert "TestPerson" in output
    assert "never reached" not in output


def test_print_graphql_errors_degrades_to_the_fallback() -> None:
    """An envelope whose entries did not match the declared shape must not exit silently."""
    console = recording_console()

    print_graphql_errors(console=console, errors=[], fallback="the raw payload the server sent")

    assert "the raw payload the server sent" in rendered(console)


def test_print_graphql_query_errors_reports_every_error() -> None:
    console = recording_console()
    exc = graphql_error_from_response(errors=[{"message": "first", "locations": [{"line": 1}]}, {"message": "second"}])

    print_graphql_query_errors(console=console, exc=exc)

    output = rendered(console)
    assert "2 error(s) occurred" in output
    assert "Message: first" in output
    assert "'line': 1" in output
    assert "Message: second" in output


def test_print_graphql_query_errors_keeps_the_branch_hint() -> None:
    """The hint reads the server's message, since a bare string never survives into `errors`."""
    console = recording_console()
    exc = graphql_error_from_response(errors=[{"message": "Branch: does-not-exist not found"}])

    print_graphql_query_errors(console=console, exc=exc)

    assert "you can specify a different branch with --branch" in rendered(console)


def test_print_graphql_query_errors_degrades_to_the_exception_message() -> None:
    console = recording_console()
    exc = graphql_error_from_response(errors=["a bare string where an array belongs"], query="query { x }")

    print_graphql_query_errors(console=console, exc=exc)

    output = rendered(console)
    assert "a bare string where an array belongs" in output
    assert "0 error(s)" not in output


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
