import asyncio
import logging
import traceback
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Coroutine, NoReturn, Optional, TypeVar, Union

import pendulum
import typer
from click.exceptions import Exit
from httpx import HTTPError
from pendulum.datetime import DateTime
from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape

from ..ctl.exceptions import FileNotValidError, QueryNotFoundError
from ..exceptions import (
    AuthenticationError,
    Error,
    GraphQLError,
    NodeNotFoundError,
    SchemaNotFoundError,
    ServerNotReachableError,
    ServerNotResponsiveError,
)
from ..schema import InfrahubRepositoryConfig
from ..yaml import YamlFile
from .client import initialize_client_sync

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
    if isinstance(exc, (SchemaNotFoundError, NodeNotFoundError)):
        console.print(f"[red]Error: {exc!s}")
        raise typer.Exit(code=exit_code)

    console.print(f"[red]Error: {exc!s}")
    console.print(traceback.format_exc())
    raise typer.Exit(code=exit_code)


def catch_exception(
    console: Optional[Console] = None, exit_code: int = 1
) -> Callable[[Callable[..., T]], Callable[..., Union[T, Coroutine[Any, Any, T]]]]:
    """Decorator to handle exception for commands."""
    if not console:
        console = Console()

    def decorator(func: Callable[..., T]) -> Callable[..., Union[T, Coroutine[Any, Any, T]]]:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                try:
                    return await func(*args, **kwargs)
                except (Error, Exception) as exc:  # pylint: disable=broad-exception-caught
                    return handle_exception(exc=exc, console=console, exit_code=exit_code)

            return async_wrapper

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return func(*args, **kwargs)
            except (Error, Exception) as exc:  # pylint: disable=broad-exception-caught
                return handle_exception(exc=exc, console=console, exit_code=exit_code)

        return wrapper

    return decorator


def execute_graphql_query(
    query: str,
    variables_dict: dict[str, Any],
    repository_config: InfrahubRepositoryConfig,
    branch: Optional[str] = None,
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


def calculate_time_diff(value: str) -> Optional[str]:
    """Calculate the time in human format between a timedate in string format and now."""
    try:
        time_value = pendulum.parse(value)
    except pendulum.parsing.exceptions.ParserError:
        return None

    if not isinstance(time_value, DateTime):
        return None

    pendulum.set_locale("en")
    return time_value.diff_for_humans(other=pendulum.now(), absolute=True)


def find_graphql_query(name: str, directory: Union[str, Path] = ".") -> str:
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

    return data_files
