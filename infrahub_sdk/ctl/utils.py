from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Coroutine
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, NoReturn, Optional, TypeVar

import typer
from click.exceptions import Exit
from httpx import HTTPError
from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape

from ..exceptions import (
    AuthenticationError,
    Error,
    FileNotValidError,
    GraphQLError,
    NodeNotFoundError,
    ResourceNotDefinedError,
    SchemaNotFoundError,
    ServerNotReachableError,
    ServerNotResponsiveError,
    ValidationError,
)
from ..yaml import YamlFile
from .client import initialize_client_sync
from .exceptions import QueryNotFoundError

if TYPE_CHECKING:
    from ..schema.repository import InfrahubRepositoryConfig
    from ..spec.object import ObjectFile

YamlFileVar = TypeVar("YamlFileVar", bound=YamlFile)
T = TypeVar("T")


def init_logging(debug: bool = False) -> None:
    """
    Initializes basic logging for CLI operations.

    Sets log levels for Infrahub SDK and HTTPX/HTTPCore libraries to minimize noise.
    Configures a RichHandler for console output.

    Args:
        debug: If True, sets the root logger level to DEBUG, otherwise INFO.
    """
    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)

    log_level = "DEBUG" if debug else "INFO"
    FORMAT = "%(message)s"
    logging.basicConfig(level=log_level, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()])
    logging.getLogger("infrahubctl")


def handle_exception(exc: Exception, console: Console, exit_code: int) -> NoReturn:
    """Handle exeception in a different fashion based on its type."""
    if isinstance(exc, Exit):
        raise typer.Exit(code=exc.exit_code)
    if isinstance(exc, AuthenticationError):
        console.print(f"[red]Authentication failure: {exc!s}")
        raise typer.Exit(code=exit_code)
    if isinstance(exc, (ServerNotReachableError, ServerNotResponsiveError)):
        console.print(f"[red]{exc!s}")
        raise typer.Exit(code=exit_code)
    if isinstance(exc, HTTPError):
        console.print(f"[red]HTTP communication failure: {exc!s} on {exc.request.method} to {exc.request.url}")
        raise typer.Exit(code=exit_code)
    if isinstance(exc, GraphQLError):
        print_graphql_errors(console=console, errors=exc.errors)
        raise typer.Exit(code=exit_code)
    if isinstance(exc, (SchemaNotFoundError, NodeNotFoundError, ResourceNotDefinedError)):
        console.print(f"[red]Error: {exc!s}")
        raise typer.Exit(code=exit_code)

    console.print(f"[red]Error: {exc!s}")
    console.print(traceback.format_exc())
    raise typer.Exit(code=exit_code)


def catch_exception(
    console: Console | None = None, exit_code: int = 1
) -> Callable[[Callable[..., T]], Callable[..., T | Coroutine[Any, Any, T]]]:
    """Decorator to handle exception for commands."""
    if not console:
        console = Console()

    def decorator(func: Callable[..., T]) -> Callable[..., T | Coroutine[Any, Any, T]]:
        if asyncio.iscoroutinefunction(func):

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
    """
    Executes a GraphQL query using the synchronous Infrahub client.

    Args:
        query: The name of the query (as defined in `repository_config`) or the query string itself.
        variables_dict: A dictionary of variables for the GraphQL query.
        repository_config: The repository configuration containing query definitions.
        branch: Optional branch name to execute the query against.
        debug: If True, prints the GraphQL response to the console.

    Returns:
        A dictionary containing the GraphQL query response.
    """
    console = Console()
    query_object = repository_config.get_query(name=query)
    query_str = query_object.load_query()

    client = initialize_client_sync()
    response = client.execute_graphql(
        query=query_str,
        branch_name=branch,
        variables=variables_dict,
        raise_for_error=False,
    )

    if debug:
        console.print("-" * 40)
        console.print(f"Response for GraphQL Query {query}")
        console.print(response)
        console.print("-" * 40)

    return response


def print_graphql_errors(console: Console, errors: list) -> None:
    """
    Prints GraphQL errors to the console with rich formatting.

    Args:
        console: The Rich Console object for printing.
        errors: A list of error objects, typically from a GraphQLError exception.
    """
    if not isinstance(errors, list):
        console.print(f"[red]{escape(str(errors))}")
        return # Ensure function exits if errors is not a list

    for error in errors:
        if isinstance(error, dict) and "message" in error and "path" in error:
            console.print(f"[red]{escape(str(error['path']))} {escape(str(error['message']))}")
        else:
            console.print(f"[red]{escape(str(error))}")


def parse_cli_vars(variables: Optional[list[str]]) -> dict[str, str]:
    """
    Parses a list of "key=value" strings into a dictionary.

    Args:
        variables: An optional list of strings, where each string is expected
                   to be in "key=value" format.

    Returns:
        A dictionary of parsed key-value pairs. Returns an empty dictionary
        if `variables` is None or empty.
    """
    if not variables:
        return {}

    return {var.split("=")[0]: var.split("=")[1] for var in variables if "=" in var}


def find_graphql_query(name: str, directory: str | Path = ".") -> str:
    """
    Searches for a GraphQL query file (.gql) by its stem name within a directory.

    Args:
        name: The stem name of the query file (without the .gql extension).
        directory: The directory to search in. Defaults to the current directory.

    Returns:
        The content of the found query file as a string.

    Raises:
        QueryNotFoundError: If no .gql file with the given stem name is found.
    """
    if isinstance(directory, str):
        directory = Path(directory)

    for query_file in directory.glob("**/*.gql"):
        if query_file.stem != name:
            continue
        return query_file.read_text(encoding="utf-8")

    raise QueryNotFoundError(name=name)


def render_action_rich(value: str) -> str:
    """
    Formats an action string (created, updated, deleted) with Rich markup for colored output.

    Args:
        value: The action string.

    Returns:
        A Rich-formatted string with color based on the action.
    """
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
    """
    Loads YAML files of a specific type from disk and exits on validation errors.

    Args:
        paths: A list of Path objects pointing to the YAML files.
        file_type: The specific YamlFile subclass to use for loading and validation
                   (e.g., SchemaFile, ObjectFile).
        console: The Rich Console object for printing error messages.

    Returns:
        A sorted list of loaded and validated YamlFileVar objects.

    Raises:
        typer.Exit: If any file is not found, invalid YAML, or fails content validation.
    """
    has_error = False
    try:
        data_files = file_type.load_from_disk(paths=paths)
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
    """
    Prints a success message to the console for a validated object file.

    Distinguishes between single-document and multi-document YAML files in the message.

    Args:
        file: The validated ObjectFile.
        console: The Rich Console object for printing.
    """
    if file.multiple_documents:
        console.print(f"[green] File '{file.location}' [{file.document_position}] is Valid!")
    else:
        console.print(f"[green] File '{file.location}' is Valid!")


def display_object_validate_format_error(file: ObjectFile, error: ValidationError, console: Console) -> None:
    """
    Prints detailed error messages to the console for an object file that failed validation.

    Distinguishes between single-document and multi-document YAML files and lists
    all specific validation error messages.

    Args:
        file: The ObjectFile that failed validation.
        error: The Pydantic ValidationError object.
        console: The Rich Console object for printing.
    """
    if file.multiple_documents:
        console.print(f"[red] File '{file.location}' [{file.document_position}] is not valid!")
    else:
        console.print(f"[red] File '{file.location}' is not valid!")
    if error.messages:
        for message in error.messages:
            console.print(f"[red] {message}")
    else:
        console.print(f"[red] {error.message}")
