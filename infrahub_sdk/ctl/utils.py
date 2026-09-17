from __future__ import annotations

import inspect
import logging
import traceback
from collections.abc import Callable, Coroutine, Sequence
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar

import typer
from httpx import HTTPError
from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape

from ..exceptions import (
    ApiError,
    AuthenticationError,
    BranchNotFoundError,
    Error,
    FileNotValidError,
    GraphQLError,
    GraphQLQueryError,
    NodeNotFoundError,
    ResourceNotDefinedError,
    SchemaNotFoundError,
    ServerNotReachableError,
    ServerNotResponsiveError,
    ValidationError,
    code_names_the_failure,
)
from ..graphql.query_renderer import render_query
from ..yaml import YamlFile
from .client import initialize_client_sync
from .exceptions import QueryNotFoundError

if TYPE_CHECKING:
    from ..schema.repository import InfrahubRepositoryConfig
    from ..spec.object import ObjectFile

YamlFileVar = TypeVar("YamlFileVar", bound=YamlFile)
T = TypeVar("T")


def init_logging(debug: bool = False) -> None:
    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)

    log_level = "DEBUG" if debug else "INFO"
    format_str = "%(message)s"
    logging.basicConfig(level=log_level, format=format_str, datefmt="[%X]", handlers=[RichHandler(show_path=debug)])
    logging.getLogger("infrahubctl")


def handle_exception(exc: Exception, console: Console, exit_code: int) -> NoReturn:
    """Handle exception in a different fashion based on its type.

    Two orderings are load-bearing, and both are here rather than in the branches that depend on
    them. The described-code branch comes first because it is the only one that can name the failure
    the way the server did, and every class-keyed branch below would either mislabel it or drop the
    code. The lookup misses come ahead of `GraphQLError`, which they now descend from and which would
    otherwise claim them and render an empty server error list in place of their message.

    Every message reaching the console is escaped: a server's own words routinely contain
    brackets (a branch name, an identifier) and rich would read those as a style tag and delete them.
    """
    if isinstance(exc, typer.Exit):
        raise exc
    if isinstance(exc, ApiError) and code_names_the_failure(exc.code):
        if exc.errors:
            # The server's errors carry the path naming the operation that failed, which the coded
            # line has nowhere to put, so they render the detail and the code just names the failure.
            console.print(f"[red]{escape(exc.code)}")
            print_graphql_errors(console=console, errors=exc.errors, raw_entry_without_path=False)
        else:
            console.print(f"[red]{escape(str(exc))}")
        raise typer.Exit(code=exit_code)
    if isinstance(exc, AuthenticationError):
        console.print(f"[red]Authentication failure: {escape(str(exc))}")
        raise typer.Exit(code=exit_code)
    if isinstance(exc, (ServerNotReachableError, ServerNotResponsiveError)):
        console.print(f"[red]{escape(str(exc))}")
        raise typer.Exit(code=exit_code)
    if isinstance(exc, HTTPError):
        console.print(
            f"[red]HTTP communication failure: {escape(str(exc))} "
            f"on {escape(str(exc.request.method))} to {escape(str(exc.request.url))}"
        )
        raise typer.Exit(code=exit_code)
    if isinstance(
        exc,
        (
            SchemaNotFoundError,
            NodeNotFoundError,
            BranchNotFoundError,
            ResourceNotDefinedError,
            GraphQLQueryError,
        ),
    ):
        console.print(f"[red]Error: {escape(str(exc))}")
        raise typer.Exit(code=exit_code)
    if isinstance(exc, GraphQLError):
        print_graphql_errors(console=console, errors=exc.errors, fallback=str(exc))
        raise typer.Exit(code=exit_code)

    console.print(f"[red]Error: {escape(str(exc))}")
    console.print(escape(traceback.format_exc()))
    raise typer.Exit(code=exit_code)


def catch_exception(
    console: Console | None = None, exit_code: int = 1
) -> Callable[[Callable[..., T]], Callable[..., T | Coroutine[Any, Any, T]]]:
    """Decorator to handle exception for commands."""
    if not console:
        console = Console()

    def decorator(func: Callable[..., T]) -> Callable[..., T | Coroutine[Any, Any, T]]:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                try:
                    return await func(*args, **kwargs)
                except (Error, Exception) as exc:
                    return handle_exception(exc=exc, console=console, exit_code=exit_code)

            return async_wrapper

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return func(*args, **kwargs)
            except (Error, Exception) as exc:
                return handle_exception(exc=exc, console=console, exit_code=exit_code)

        return wrapper

    return decorator


def execute_graphql_query(
    query: str,
    variables_dict: dict[str, Any],
    repository_config: InfrahubRepositoryConfig,
    branch: str | None = None,
    debug: bool = False,
) -> dict:
    console = Console()
    query_str = render_query(name=query, config=repository_config)

    client = initialize_client_sync()

    if not branch:
        branch = client.config.default_infrahub_branch

    response = client.execute_graphql(
        query=query_str,
        branch_name=branch,
        variables=variables_dict,
    )

    if debug:
        console.print("-" * 40)
        console.print(f"Response for GraphQL Query {query}")
        console.print(response)
        console.print("-" * 40)

    return response


def print_graphql_errors(
    console: Console,
    errors: Sequence[dict[str, Any]],
    fallback: str | None = None,
    raw_entry_without_path: bool = True,
) -> None:
    """Render the server's errors, degrading to `fallback` when there is nothing to render.

    An envelope whose entries did not match the declared shape leaves `errors` empty, and exiting
    non-zero with no output at all would tell the user nothing.

    `raw_entry_without_path` decides what an entry carrying no path renders as. By default the whole
    decoded entry prints, because a validation error carries `locations` instead of a path and those
    coordinates are the useful part. A caller that has already printed a line naming the failure
    passes `False`, so the rest read as the server's sentences rather than as decoded dicts.
    """
    if not errors:
        if fallback:
            console.print(f"[red]{escape(fallback)}")
        return

    for error in errors:
        # An explicit null path is as good as an absent one; keying on the key alone renders "None"
        # in front of the message.
        path = error.get("path") if isinstance(error, dict) else None
        if isinstance(error, dict) and "message" in error and path is not None:
            console.print(f"[red]{escape(str(path))} {escape(str(error['message']))}")
        elif raw_entry_without_path or not isinstance(error, dict):
            console.print(f"[red]{escape(str(error))}")
        else:
            console.print(f"[red]{escape(str(error.get('message', error)))}")


def print_graphql_query_errors(console: Console, exc: GraphQLError) -> None:
    """Render the failure of a GraphQL query the CLI ran on the user's behalf.

    The branch hint is keyed on the server's message rather than on the entry's Python type, because
    the exception's `errors` are dicts by construction and a bare string never reaches here.
    """
    if not exc.errors:
        console.print(f"[red]{escape(str(exc))}")
        return

    console.print(f"[red]{len(exc.errors)} error(s) occurred while executing the query")
    for error in exc.errors:
        message = str(error.get("message", error))
        console.print(f"[yellow] - Message: {escape(message)}")
        if "locations" in error:
            console.print(f"[yellow]   Location: {escape(str(error['locations']))}")
        if "Branch:" in message:
            console.print("[yellow]   you can specify a different branch with --branch")


def parse_cli_vars(variables: list[str] | None) -> dict[str, str]:
    if not variables:
        return {}

    return {var.split("=")[0]: var.split("=")[1] for var in variables if "=" in var}


def find_graphql_query(name: str, directory: str | Path = ".") -> str:
    if isinstance(directory, str):
        directory = Path(directory)

    for query_file in directory.glob("**/*.gql"):
        if query_file.stem != name:
            continue
        return query_file.read_text(encoding="utf-8")

    raise QueryNotFoundError(name=name)


def render_action_rich(value: str) -> str:
    if value == "created":
        return f"[green]{value.upper()}[/green]"
    if value == "updated":
        return f"[magenta]{value.upper()}[/magenta]"
    if value == "deleted":
        return f"[red]{value.upper()}[/red]"

    return value.upper()


def get_fixtures_dir() -> Path:
    """Get the directory which stores fixtures that are common to multiple unit/integration tests."""
    here = Path(__file__).resolve().parent
    return here.parent.parent / "tests" / "fixtures"


def load_yamlfile_from_disk_and_exit(
    paths: list[Path], file_type: type[YamlFileVar], console: Console
) -> list[YamlFileVar]:
    has_error = False
    try:
        data_files = file_type.load_from_disk(paths=paths)
        if not data_files:
            console.print("[red]No valid files found to load.")
            raise typer.Exit(1)
    except FileNotValidError as exc:
        console.print(f"[red]{exc.message}")
        raise typer.Exit(1) from exc

    for data_file in data_files:
        if data_file.valid and data_file.content:
            continue
        console.print(f"[red]{data_file.error_message} ({data_file.location})")
        has_error = True

    if has_error:
        raise typer.Exit(1)

    return sorted(data_files, key=lambda x: x.location)


def display_object_validate_format_success(file: ObjectFile, console: Console) -> None:
    if file.multiple_documents:
        console.print(f"[green] File '{file.location}' [{file.document_position}] is Valid!")
    else:
        console.print(f"[green] File '{file.location}' is Valid!")


def display_object_validate_format_error(file: ObjectFile, error: ValidationError, console: Console) -> None:
    if file.multiple_documents:
        console.print(f"[red] File '{file.location}' [{file.document_position}] is not valid!")
    else:
        console.print(f"[red] File '{file.location}' is not valid!")
    if error.messages:
        for message in error.messages:
            console.print(f"[red] {message}")
    else:
        console.print(f"[red] {error.message}")
