import json
from io import StringIO
from typing import Any

import httpx
import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl.utils import (
    catch_exception,
    handle_exception,
    print_graphql_errors,
    print_graphql_query_errors,
)
from infrahub_sdk.exceptions import (
    AuthenticationError,
    BranchNotFoundError,
    NodeNotFoundError,
    SchemaNotFoundError,
    authentication_error_from_response,
    graphql_error_from_response,
)
from tests.helpers.cli import remove_ansi_color
from tests.helpers.fixtures import read_fixture

runner = CliRunner()

FIXTURE_SUBDIR = "error_catalogue"


def rendered(recorder: Console) -> str:
    return remove_ansi_color(recorder.file.getvalue())  # type: ignore[attr-defined]


def recording_console() -> Console:
    """A console that captures its output instead of writing it to the terminal."""
    return Console(record=True, file=StringIO(), width=200)


def load_envelope(name: str) -> dict[str, Any]:
    return json.loads(read_fixture(file_name=name, fixture_subdir=FIXTURE_SUBDIR))


def rendered_for(exc: Exception) -> str:
    """Drive the ladder and return what the user would have seen."""
    console = recording_console()

    with pytest.raises(typer.Exit):
        handle_exception(exc=exc, console=console, exit_code=1)

    return rendered(console)


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


class TestHandleExceptionLadder:
    """Asserts the rendering each class reaches, rather than reading the order off the source."""

    def test_a_node_lookup_miss_is_not_rendered_as_a_graphql_failure(self) -> None:
        """Re-rooting puts this class under `GraphQLError`, whose branch would print an error list."""
        output = rendered_for(NodeNotFoundError(identifier={"name": ["john"]}, node_type="TestPerson"))

        assert "Error: " in output
        assert "TestPerson" in output
        assert "error(s) occurred" not in output

    def test_a_schema_lookup_miss_keeps_its_own_rendering(self) -> None:
        output = rendered_for(SchemaNotFoundError(identifier="TestPerson"))

        assert "Error: Unable to find the schema 'TestPerson'." in output

    def test_a_catalogued_graphql_failure_names_the_code_and_the_server_message(self) -> None:
        envelope = load_envelope("graphql_uniqueness_violation.json")
        exc = graphql_error_from_response(errors=envelope["errors"], query="mutation { TestPersonCreate }")

        output = rendered_for(exc)

        assert "UNIQUENESS_VIOLATION" in output
        assert "already has name" in output
        assert "mutation { TestPersonCreate }" not in output

    def test_a_single_error_keeps_the_path_naming_the_failed_operation(self) -> None:
        """The coded line has nowhere to put the path, so the error list still has to render."""
        envelope = load_envelope("graphql_uniqueness_violation.json")
        exc = graphql_error_from_response(errors=envelope["errors"])

        output = rendered_for(exc)

        assert "TestPersonCreate" in output, "the path tells the user which operation failed"

    def test_the_governing_message_is_not_printed_twice(self) -> None:
        output = rendered_for(
            graphql_error_from_response(errors=load_envelope("graphql_uniqueness_violation.json")["errors"])
        )

        assert output.count("already has name") == 1

    def test_a_catalogued_authentication_failure_is_named_rather_than_labelled(self) -> None:
        """Labelling every 401 an authentication failure mislabels PERMISSION_DENIED, so the code wins."""
        request = httpx.Request("POST", "http://mock/graphql/main")
        response = httpx.Response(status_code=401, json=load_envelope("auth_token_expired.json"), request=request)
        exc = authentication_error_from_response(response=response)

        output = rendered_for(exc)

        assert "TOKEN_EXPIRED" in output
        assert "Expired Signature" in output
        assert "Authentication failure" not in output
        assert "extensions" not in output, "an envelope with no path must not render as a raw dict"

    def test_an_uncatalogued_authentication_failure_keeps_todays_rendering(self) -> None:
        """Only errors carrying a code take the new branch; everything else is unchanged."""
        output = rendered_for(AuthenticationError("no token supplied"))

        assert "Authentication failure: no token supplied" in output

    def test_a_branch_lookup_miss_is_not_rendered_as_a_graphql_failure(self) -> None:
        """Re-rooted alongside the other two, so it owes the same rendering as the other two."""
        output = rendered_for(BranchNotFoundError(identifier="does-not-exist"))

        assert "Error: Unable to find the branch 'does-not-exist' in the Database." in output
        assert "error(s) occurred" not in output

    def test_a_server_message_is_not_read_as_console_markup(self) -> None:
        """Rich eats anything shaped like a tag, and a branch name in brackets is exactly that."""
        exc = graphql_error_from_response(
            errors=[{"message": "Branch [main] does not exist", "extensions": {"code": "BRANCH_NOT_FOUND"}}]
        )

        output = rendered_for(exc)

        assert "Branch [main] does not exist" in output

    def test_every_server_error_is_rendered_not_just_the_governing_one(self) -> None:
        """The code names the first error only, so the rest must still reach the user."""
        envelope = load_envelope("graphql_multiple_errors.json")
        exc = graphql_error_from_response(errors=envelope["errors"])

        output = rendered_for(exc)

        assert "SCHEMA_NOT_FOUND" in output
        assert "first failure" in output
        assert "second failure" in output
        assert "third failure" in output

    def test_an_uncatalogued_error_without_a_path_keeps_its_raw_entry(self) -> None:
        """A validation error carries `locations` and no `path`, and those coordinates are the point.

        Uncatalogued rendering is unchanged by this feature, so the whole entry still prints.
        """
        exc = graphql_error_from_response(
            errors=[{"message": "Cannot query field 'nope'.", "locations": [{"line": 1, "column": 9}]}],
            query="query { nope }",
        )

        output = rendered_for(exc)

        assert "'line': 1" in output
        assert "'column': 9" in output

    def test_an_uncatalogued_graphql_failure_still_renders_the_server_errors(self) -> None:
        exc = graphql_error_from_response(errors=[{"message": "boom", "path": ["TestPerson"]}])

        output = rendered_for(exc)

        assert "boom" in output
        assert "TestPerson" in output


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
