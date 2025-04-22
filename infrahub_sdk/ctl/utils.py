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
    if not isinstance(errors, list):
        console.print(f"[red]{escape(str(errors))}")

    for error in errors:
        if isinstance(error, dict) and "message" in error and "path" in error:
            console.print(f"[red]{escape(str(error['path']))} {escape(str(error['message']))}")
        else:
            console.print(f"[red]{escape(str(error))}")


def parse_cli_vars(variables: Optional[list[str]]) -> dict[str, str]:
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
