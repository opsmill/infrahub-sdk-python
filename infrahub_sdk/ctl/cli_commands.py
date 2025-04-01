from __future__ import annotations

import asyncio
import functools
import importlib
import logging
import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import typer
import ujson
from rich.console import Console
from rich.layout import Layout
from rich.logging import RichHandler
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table

from .. import __version__ as sdk_version
from ..async_typer import AsyncTyper
from ..code_generator import CodeGenerator
from ..ctl import config
from ..ctl.branch import app as branch_app
from ..ctl.check import run as run_check
from ..ctl.client import initialize_client, initialize_client_sync
from ..ctl.exceptions import QueryNotFoundError
from ..ctl.generator import run as run_generator
from ..ctl.menu import app as menu_app
from ..ctl.object import app as object_app
from ..ctl.render import list_jinja2_transforms, print_template_errors
from ..ctl.repository import app as repository_app
from ..ctl.repository import get_repository_config
from ..ctl.schema import app as schema_app
from ..ctl.transform import list_transforms
from ..ctl.utils import (
    catch_exception,
    execute_graphql_query,
    load_yamlfile_from_disk_and_exit,
    parse_cli_vars,
)
from ..ctl.validate import app as validate_app
from ..exceptions import GraphQLError, ModuleImportError
from ..schema import MainSchemaTypesAll, SchemaRoot
from ..template import Jinja2Template
from ..template.exceptions import JinjaTemplateError
from ..utils import get_branch, write_to_file
from ..yaml import SchemaFile
from .exporter import dump
from .importer import load
from .parameters import CONFIG_PARAM

if TYPE_CHECKING:
    from ..schema.repository import InfrahubRepositoryConfig

app = AsyncTyper(pretty_exceptions_show_locals=False)

app.add_typer(branch_app, name="branch")
app.add_typer(schema_app, name="schema")
app.add_typer(validate_app, name="validate")
app.add_typer(repository_app, name="repository")
app.add_typer(menu_app, name="menu")
app.add_typer(object_app, name="object", hidden=True)

app.command(name="dump")(dump)
app.command(name="load")(load)

console = Console()


@app.command(name="check")
@catch_exception(console=console)
def check(
    check_name: str = typer.Argument(default="", help="Name of the Python check"),
    branch: Optional[str] = None,
    path: str = typer.Option(".", help="Root directory"),
    debug: bool = False,
    format_json: bool = False,
    _: str = CONFIG_PARAM,
    list_available: bool = typer.Option(False, "--list", help="Show available Python checks"),
    variables: Optional[list[str]] = typer.Argument(
        None, help="Variables to pass along with the query. Format key=value key=value."
    ),
) -> None:
    """Execute user-defined checks."""

    variables_dict = parse_cli_vars(variables)
    run_check(
        path=path,
        debug=debug,
        branch=branch,
        format_json=format_json,
        list_available=list_available,
        name=check_name,
        variables=variables_dict,
    )


@app.command(name="generator")
@catch_exception(console=console)
async def generator(
    generator_name: str = typer.Argument(default="", help="Name of the Generator"),
    branch: Optional[str] = None,
    path: str = typer.Option(".", help="Root directory"),
    debug: bool = False,
    _: str = CONFIG_PARAM,
    list_available: bool = typer.Option(False, "--list", help="Show available Generators"),
    variables: Optional[list[str]] = typer.Argument(
        None, help="Variables to pass along with the query. Format key=value key=value."
    ),
) -> None:
    """Run a generator script."""
    await run_generator(
        generator_name=generator_name,
        branch=branch,
        path=path,
        debug=debug,
        list_available=list_available,
        variables=variables,
    )


@app.command(name="run")
@catch_exception(console=console)
async def run(
    script: Path,
    method: str = "run",
    debug: bool = False,
    _: str = CONFIG_PARAM,
    branch: str = typer.Option(None, help="Branch on which to run the script."),
    concurrent: Optional[int] = typer.Option(
        None,
        help="Maximum number of requests to execute at the same time.",
        envvar="INFRAHUB_MAX_CONCURRENT_EXECUTION",
    ),
    timeout: int = typer.Option(60, help="Timeout in sec", envvar="INFRAHUB_TIMEOUT"),
    variables: Optional[list[str]] = typer.Argument(
        None, help="Variables to pass along with the query. Format key=value key=value."
    ),
) -> None:
    """Execute a script."""

    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)

    log_level = "DEBUG" if debug else "INFO"
    FORMAT = "%(message)s"
    logging.basicConfig(level=log_level, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()])
    log = logging.getLogger("infrahubctl")

    variables_dict = parse_cli_vars(variables)

    directory_name = str(script.parent)
    module_name = script.stem

    if directory_name not in sys.path:
        sys.path.append(directory_name)

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise typer.Abort(f"Unable to Load the Python script at {script}") from exc

    if not hasattr(module, method):
        raise typer.Abort(f"Unable to Load the method {method} in the Python script at {script}")

    client = initialize_client(
        branch=branch,
        timeout=timeout,
        max_concurrent_execution=concurrent,
        identifier=module_name,
    )
    func = getattr(module, method)
    await func(client=client, log=log, branch=branch, **variables_dict)


async def render_jinja2_template(template_path: Path, variables: dict[str, Any], data: dict[str, Any]) -> str:
    variables["data"] = data
    jinja_template = Jinja2Template(template=Path(template_path), template_directory=Path())
    try:
        rendered_tpl = await jinja_template.render(variables=variables)
    except JinjaTemplateError as exc:
        print_template_errors(error=exc, console=console)
        raise typer.Exit(1) from exc

    return rendered_tpl


async def _run_transform(
    query_name: str,
    variables: dict[str, Any],
    transform_func: Callable,
    branch: str,
    debug: bool,
    repository_config: InfrahubRepositoryConfig,
) -> Any:
    """
    Query GraphQL for the required data then run a transform on that data.

    Args:
        query_name: Name of the query to load (e.g. tags_query)
        variables: Dictionary of variables used for graphql query
        transform_func: The function responsible for transforming data received from graphql
        branch: Name of the *infrahub* branch that should be queried for data
        debug: Prints debug info to the command line
        repository_config: Repository config object. This is used to load the graphql query from the repository.
    """
    branch = get_branch(branch)

    try:
        response = execute_graphql_query(
            query=query_name,
            variables_dict=variables,
            branch=branch,
            debug=debug,
            repository_config=repository_config,
        )

        # TODO: response is a dict and can't be printed to the console in this way.
        # if debug:
        #     message = ("-" * 40, f"Response for GraphQL Query {query_name}", response, "-" * 40)
        #     console.print("\n".join(message))
    except QueryNotFoundError as exc:
        console.print(f"[red]Unable to find query : {exc}")
        raise typer.Exit(1) from exc
    except GraphQLError as exc:
        console.print(f"[red]{len(exc.errors)} error(s) occurred while executing the query")
        for error in exc.errors:
            if isinstance(error, dict) and "message" in error and "locations" in error:
                console.print(f"[yellow] - Message: {error['message']}")  # type: ignore[typeddict-item]
                console.print(f"[yellow]   Location: {error['locations']}")  # type: ignore[typeddict-item]
            elif isinstance(error, str) and "Branch:" in error:
                console.print(f"[yellow] - {error}")
                console.print("[yellow]   you can specify a different branch with --branch")
        raise typer.Abort()

    if asyncio.iscoroutinefunction(transform_func):
        output = await transform_func(response)
    else:
        output = transform_func(response)
    return output


@app.command(name="render")
@catch_exception(console=console)
async def render(
    transform_name: str = typer.Argument(default="", help="Name of the Python transformation", show_default=False),
    variables: Optional[list[str]] = typer.Argument(
        None, help="Variables to pass along with the query. Format key=value key=value."
    ),
    branch: str = typer.Option(None, help="Branch on which to render the transform."),
    debug: bool = False,
    _: str = CONFIG_PARAM,
    list_available: bool = typer.Option(False, "--list", help="Show available transforms"),
    out: str = typer.Option(None, help="Path to a file to save the result."),
) -> None:
    """Render a local Jinja2 Transform for debugging purpose."""

    variables_dict = parse_cli_vars(variables)
    repository_config = get_repository_config(Path(config.INFRAHUB_REPO_CONFIG_FILE))

    if list_available or not transform_name:
        list_jinja2_transforms(config=repository_config)
        return

    # Load transform config
    try:
        transform_config = repository_config.get_jinja2_transform(name=transform_name)
    except KeyError as exc:
        console.print(f'[red]Unable to find "{transform_name}" in {config.INFRAHUB_REPO_CONFIG_FILE}')
        list_jinja2_transforms(config=repository_config)
        raise typer.Exit(1) from exc

    # Construct transform function used to transform data returned from the API
    transform_func = functools.partial(render_jinja2_template, transform_config.template_path, variables_dict)

    # Query GQL and run the transform
    result = await _run_transform(
        query_name=transform_config.query,
        variables=variables_dict,
        transform_func=transform_func,
        branch=branch,
        debug=debug,
        repository_config=repository_config,
    )

    # Output data
    if out:
        write_to_file(Path(out), result)
    else:
        console.print(result)


@app.command(name="transform")
@catch_exception(console=console)
def transform(
    transform_name: str = typer.Argument(default="", help="Name of the Python transformation", show_default=False),
    variables: Optional[list[str]] = typer.Argument(
        None, help="Variables to pass along with the query. Format key=value key=value."
    ),
    branch: str = typer.Option(None, help="Branch on which to run the transformation"),
    debug: bool = False,  # noqa: ARG001
    _: str = CONFIG_PARAM,
    list_available: bool = typer.Option(False, "--list", help="Show available transforms"),
    out: str = typer.Option(None, help="Path to a file to save the result."),
) -> None:
    """Render a local transform (TransformPython) for debugging purpose."""

    variables_dict = parse_cli_vars(variables)
    repository_config = get_repository_config(Path(config.INFRAHUB_REPO_CONFIG_FILE))

    if list_available or not transform_name:
        list_transforms(config=repository_config)
        return

    transform_config = repository_config.get_python_transform(name=transform_name)

    # Get client
    client = initialize_client(branch=branch)

    # Get python transform class instance

    relative_path = str(transform_config.file_path.parent) if transform_config.file_path.parent != Path() else None

    try:
        transform_class = transform_config.load_class(import_root=str(Path.cwd()), relative_path=relative_path)
    except ModuleImportError as exc:
        console.print(f"[red]{exc.message}")
        raise typer.Exit(1) from exc

    transform = transform_class(client=client, branch=branch)
    # Get data
    query_str = repository_config.get_query(name=transform.query).load_query()
    data = asyncio.run(
        transform.client.execute_graphql(query=query_str, variables=variables_dict, branch_name=transform.branch_name)
    )

    # Run Transform
    result = asyncio.run(transform.run(data=data))

    if isinstance(result, str):
        json_string = result
    else:
        json_string = ujson.dumps(result, indent=2, sort_keys=True)

    if out:
        write_to_file(Path(out), json_string)
    else:
        console.print(json_string)


@app.command(name="protocols")
@catch_exception(console=console)
def protocols(
    schemas: list[Path] = typer.Option(None, help="List of schemas or directory to load."),
    branch: str = typer.Option(None, help="Branch of schema to export Python protocols for."),
    sync: bool = typer.Option(False, help="Generate for sync or async."),
    _: str = CONFIG_PARAM,
    out: str = typer.Option("schema_protocols.py", help="Path to a file to save the result."),
) -> None:
    """Export Python protocols corresponding to a schema."""

    schema: dict[str, MainSchemaTypesAll] = {}

    if schemas:
        schemas_data = load_yamlfile_from_disk_and_exit(paths=schemas, file_type=SchemaFile, console=console)

        for data in schemas_data:
            data.load_content()
            schema_root_data = data.content or {}
            schema_root = SchemaRoot(**schema_root_data)
            schema.update({item.kind: item for item in schema_root.nodes + schema_root.generics})

    else:
        client = initialize_client_sync()
        branch = branch or client.default_branch
        schema.update(client.schema.fetch(branch=branch))

    code_generator = CodeGenerator(schema=schema)

    if out:
        output_file = Path(out)
        write_to_file(output_file, code_generator.render(sync=sync))
        console.print(f"Python protocols exported in {output_file}")
    else:
        console.print(code_generator.render(sync=sync))


@app.command(name="version")
@catch_exception(console=console)
def version() -> None:
    """Display the version of Python and the version of the Python SDK in use."""

    console.print(f"Python: {platform.python_version()}\nPython SDK: v{sdk_version}")


@app.command(name="info")
@catch_exception(console=console)
def info(  # noqa: PLR0915
    detail: bool = typer.Option(False, help="Display detailed information."),
    _: str = CONFIG_PARAM,
) -> None:
    """Display the status of the Python SDK."""

    info: dict[str, Any] = {
        "error": None,
        "status": ":x:",
        "infrahub_version": "N/A",
        "user_info": {},
        "groups": {},
    }
    try:
        client = initialize_client_sync()
        info["infrahub_version"] = client.get_version()
        info["user_info"] = client.get_user()
        info["status"] = ":white_heavy_check_mark:"
        info["groups"] = client.get_user_permissions()
    except Exception as e:
        info["error"] = f"{e!s} ({e.__class__.__name__})"

    if detail:
        layout = Layout()

        # Layout structure
        new_console = Console(height=45)
        layout = Layout()
        layout.split_column(
            Layout(name="body", ratio=1),
        )
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )

        layout["left"].split_column(
            Layout(name="connection_status", size=7),
            Layout(name="client_info", ratio=1),
        )

        layout["right"].split_column(
            Layout(name="version_info", size=7),
            Layout(name="infrahub_info", ratio=1),
        )

        # Connection status panel
        connection_status = Table(show_header=False, box=None)
        connection_status.add_row("Server Address:", client.config.address)
        connection_status.add_row("Status:", info["status"])
        if info["error"]:
            connection_status.add_row("Error Reason:", info["error"])
        layout["connection_status"].update(Panel(connection_status, title="Connection Status"))

        # Version information panel
        version_info = Table(show_header=False, box=None)
        version_info.add_row("Python Version:", platform.python_version())
        version_info.add_row("Infrahub Version", info["infrahub_version"])
        version_info.add_row("Infrahub SDK:", sdk_version)
        layout["version_info"].update(Panel(version_info, title="Version Information"))

        # SDK client configuration panel
        pretty_model = Pretty(client.config.model_dump(), expand_all=True)
        layout["client_info"].update(Panel(pretty_model, title="Client Info"))

        # Infrahub information planel
        infrahub_info = Table(show_header=False, box=None)
        if info["user_info"]:
            infrahub_info.add_row("User:", info["user_info"]["AccountProfile"]["display_label"])
            infrahub_info.add_row(
                "Description:",
                info["user_info"]["AccountProfile"]["description"]["value"],
            )
            infrahub_info.add_row("Status:", info["user_info"]["AccountProfile"]["status"]["label"])
            infrahub_info.add_row(
                "Number of Groups:",
                str(info["user_info"]["AccountProfile"]["member_of_groups"]["count"]),
            )

            if groups := info["groups"]:
                infrahub_info.add_row("Groups:", "")
                for group, roles in groups.items():
                    infrahub_info.add_row("", group, ", ".join(roles))

        layout["infrahub_info"].update(Panel(infrahub_info, title="Infrahub Info"))

        new_console.print(layout)
    else:
        # Simple output
        table = Table(show_header=False, box=None)
        table.add_row("Address:", client.config.address)
        table.add_row("Connection Status:", info["status"])
        if info["error"]:
            table.add_row("Connection Error:", info["error"])

        table.add_row("Python Version:", platform.python_version())
        table.add_row("SDK Version:", sdk_version)
        table.add_row("Infrahub Version:", info["infrahub_version"])
        if account := info["user_info"].get("AccountProfile"):
            table.add_row("User:", account["display_label"])

        console.print(table)
