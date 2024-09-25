import asyncio
import functools
import importlib
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional, Union

import jinja2
import typer
import ujson
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import Traceback

from infrahub_sdk import __version__ as sdk_version
from infrahub_sdk import protocols as sdk_protocols
from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl import config
from infrahub_sdk.ctl.branch import app as branch_app
from infrahub_sdk.ctl.check import run as run_check
from infrahub_sdk.ctl.client import initialize_client, initialize_client_sync
from infrahub_sdk.ctl.constants import PROTOCOLS_TEMPLATE
from infrahub_sdk.ctl.exceptions import QueryNotFoundError
from infrahub_sdk.ctl.generator import run as run_generator
from infrahub_sdk.ctl.render import list_jinja2_transforms
from infrahub_sdk.ctl.repository import app as repository_app
from infrahub_sdk.ctl.repository import get_repository_config
from infrahub_sdk.ctl.schema import app as schema
from infrahub_sdk.ctl.transform import list_transforms
from infrahub_sdk.ctl.utils import catch_exception, execute_graphql_query, parse_cli_vars
from infrahub_sdk.ctl.validate import app as validate_app
from infrahub_sdk.exceptions import GraphQLError, InfrahubTransformNotFoundError
from infrahub_sdk.jinja2 import identify_faulty_jinja_code
from infrahub_sdk.schema import (
    AttributeSchema,
    GenericSchema,
    InfrahubRepositoryConfig,
    InfrahubRepositoryGraphQLConfig,
    NodeSchema,
    RelationshipSchema,
)
from infrahub_sdk.transforms import get_transform_class_instance
from infrahub_sdk.utils import get_branch, write_to_file

from .exporter import dump
from .importer import load
from .parameters import CONFIG_PARAM

app = AsyncTyper(pretty_exceptions_show_locals=False)

app.add_typer(branch_app, name="branch")
app.add_typer(schema, name="schema")
app.add_typer(validate_app, name="validate")
app.add_typer(repository_app, name="repository")
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
    branch: str = typer.Option("main", help="Branch on which to run the script."),
    concurrent: int = typer.Option(
        4,
        help="Maximum number of requests to execute at the same time.",
        envvar="INFRAHUBCTL_CONCURRENT_EXECUTION",
    ),
    timeout: int = typer.Option(60, help="Timeout in sec", envvar="INFRAHUBCTL_TIMEOUT"),
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

    client = await initialize_client(
        branch=branch, timeout=timeout, max_concurrent_execution=concurrent, identifier=module_name
    )
    func = getattr(module, method)
    await func(client=client, log=log, branch=branch, **variables_dict)


def render_jinja2_template(template_path: Path, variables: dict[str, str], data: dict[str, Any]) -> str:
    if not template_path.is_file():
        console.print(f"[red]Unable to locate the template at {template_path}")
        raise typer.Exit(1)

    templateLoader = jinja2.FileSystemLoader(searchpath=".")
    templateEnv = jinja2.Environment(loader=templateLoader, trim_blocks=True, lstrip_blocks=True)
    template = templateEnv.get_template(str(template_path))

    try:
        rendered_tpl = template.render(**variables, data=data)  # type: ignore[arg-type]
    except jinja2.TemplateSyntaxError as exc:
        console.print("[red]Syntax Error detected on the template")
        console.print(f"[yellow]  {exc}")
        raise typer.Exit(1) from exc

    except jinja2.UndefinedError as exc:
        console.print("[red]An error occurred while rendering the jinja template")
        traceback = Traceback(show_locals=False)
        errors = identify_faulty_jinja_code(traceback=traceback)
        for frame, syntax in errors:
            console.print(f"[yellow]{frame.filename} on line {frame.lineno}\n")
            console.print(syntax)
        console.print("")
        console.print(traceback.trace.stacks[0].exc_value)
        raise typer.Exit(1) from exc

    return rendered_tpl


def _run_transform(
    query_name: str,
    variables: dict[str, Any],
    transform_func: Callable,
    branch: str,
    debug: bool,
    repository_config: InfrahubRepositoryConfig,
):
    """
    Query GraphQL for the required data then run a transform on that data.

    Args:
        query_name: Name of the query to load (e.g. tags_query)
        variables: Dictionary of variables used for graphql query
        transformer_func: The function responsible for transforming data received from graphql
        transform: A function used to transform the return from the graphql query into a different form
        branch: Name of the *infrahub* branch that should be queried for data
        debug: Prints debug info to the command line
        repository_config: Repository config object. This is used to load the graphql query from the repository.
    """
    branch = get_branch(branch)

    try:
        response = execute_graphql_query(
            query=query_name, variables_dict=variables, branch=branch, debug=debug, repository_config=repository_config
        )

        if debug:
            message = ("-" * 40, f"Response for GraphQL Query {query_name}", response, "-" * 40)
            console.print("\n".join(message))
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
        output = asyncio.run(transform_func(response))
    else:
        output = transform_func(response)
    return output


@app.command(name="render")
@catch_exception(console=console)
def render(
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

    if list_available:
        list_jinja2_transforms(config=repository_config)
        return

    # Load transform config
    try:
        transform_config = repository_config.get_jinja2_transform(name=transform_name)
    except KeyError as exc:
        console.print(f'[red]Unable to find "{transform_name}" in {config.INFRAHUB_REPO_CONFIG_FILE}')
        list_jinja2_transforms(config=repository_config)
        raise typer.Exit(1) from exc

    # Load query config object and add to repository config
    query_config_obj = InfrahubRepositoryGraphQLConfig(
        name=transform_config.query, file_path=Path(transform_config.query + ".gql")
    )
    repository_config.queries.append(query_config_obj)

    # Construct transform function used to transform data returned from the API
    transform_func = functools.partial(render_jinja2_template, transform_config.template_path, variables_dict)

    # Query GQL and run the transform
    result = _run_transform(
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
    debug: bool = False,
    _: str = CONFIG_PARAM,
    list_available: bool = typer.Option(False, "--list", help="Show available transforms"),
    out: str = typer.Option(None, help="Path to a file to save the result."),
) -> None:
    """Render a local transform (TransformPython) for debugging purpose."""

    variables_dict = parse_cli_vars(variables)
    repository_config = get_repository_config(Path(config.INFRAHUB_REPO_CONFIG_FILE))

    if list_available:
        list_transforms(config=repository_config)
        return

    # Load transform config
    try:
        matched = [transform for transform in repository_config.python_transforms if transform.name == transform_name]  # pylint: disable=not-an-iterable
        if not matched:
            raise ValueError(f"{transform_name} does not exist")
    except ValueError as exc:
        console.print(f"[red]Unable to find requested transform: {transform_name}")
        list_transforms(config=repository_config)
        raise typer.Exit(1) from exc

    transform_config = matched[0]

    # Get python transform class instance
    try:
        transform = get_transform_class_instance(
            transform_config=transform_config, branch=branch, repository_config=repository_config
        )
    except InfrahubTransformNotFoundError as exc:
        console.print(f"Unable to load {transform_name} from python_transforms")
        raise typer.Exit(1) from exc

    # Load query config
    query_config_obj = InfrahubRepositoryGraphQLConfig(name=transform.query, file_path=Path(transform.query + ".gql"))
    repository_config.queries.append(query_config_obj)

    # Run Transform
    result = asyncio.run(transform.run(variables=variables_dict))

    json_string = ujson.dumps(result, indent=2, sort_keys=True)
    if out:
        write_to_file(Path(out), json_string)
    else:
        console.print(json_string)


@app.command(name="protocols")
@catch_exception(console=console)
def protocols(  # noqa: PLR0915
    branch: str = typer.Option(None, help="Branch of schema to export Python protocols for."),
    _: str = CONFIG_PARAM,
    out: str = typer.Option("schema_protocols.py", help="Path to a file to save the result."),
) -> None:
    """Export Python protocols corresponding to a schema."""

    def _jinja2_filter_inheritance(value: dict[str, Any]) -> str:
        inherit_from: list[str] = value.get("inherit_from", [])

        if not inherit_from:
            return "CoreNode"
        return ", ".join(inherit_from)

    def _jinja2_filter_render_attribute(value: AttributeSchema) -> str:
        attribute_kind_map = {
            "boolean": "bool",
            "datetime": "datetime",
            "dropdown": "str",
            "hashedpassword": "str",
            "iphost": "str",
            "ipnetwork": "str",
            "json": "dict",
            "list": "list",
            "number": "int",
            "password": "str",
            "text": "str",
            "textarea": "str",
            "url": "str",
        }

        name = value.name
        kind = value.kind

        attribute_kind = attribute_kind_map[kind.lower()]
        if value.optional:
            attribute_kind = f"Optional[{attribute_kind}]"

        return f"{name}: {attribute_kind}"

    def _jinja2_filter_render_relationship(value: RelationshipSchema, sync: bool = False) -> str:
        name = value.name
        cardinality = value.cardinality

        type_ = "RelatedNode"
        if cardinality == "many":
            type_ = "RelationshipManager"

        if sync:
            type_ += "Sync"

        return f"{name}: {type_}"

    def _sort_and_filter_models(
        models: dict[str, Union[GenericSchema, NodeSchema]], filters: Optional[list[str]] = None
    ) -> list[Union[GenericSchema, NodeSchema]]:
        if filters is None:
            filters = ["CoreNode"]

        filtered: list[Union[GenericSchema, NodeSchema]] = []
        for name, model in models.items():
            if name in filters:
                continue
            filtered.append(model)

        return sorted(filtered, key=lambda k: k.name)

    client = initialize_client_sync()
    current_schema = client.schema.all(branch=branch)

    generics: dict[str, GenericSchema] = {}
    nodes: dict[str, NodeSchema] = {}

    for name, schema_type in current_schema.items():
        if isinstance(schema_type, GenericSchema):
            generics[name] = schema_type
        if isinstance(schema_type, NodeSchema):
            nodes[name] = schema_type

    base_protocols = [
        e
        for e in dir(sdk_protocols)
        if not e.startswith("__")
        and not e.endswith("__")
        and e not in ("TYPE_CHECKING", "CoreNode", "Optional", "Protocol", "Union", "annotations", "runtime_checkable")
    ]
    sorted_generics = _sort_and_filter_models(generics, filters=["CoreNode"] + base_protocols)
    sorted_nodes = _sort_and_filter_models(nodes, filters=["CoreNode"] + base_protocols)

    jinja2_env = jinja2.Environment(loader=jinja2.BaseLoader, trim_blocks=True, lstrip_blocks=True)
    jinja2_env.filters["inheritance"] = _jinja2_filter_inheritance
    jinja2_env.filters["render_attribute"] = _jinja2_filter_render_attribute
    jinja2_env.filters["render_relationship"] = _jinja2_filter_render_relationship

    template = jinja2_env.from_string(PROTOCOLS_TEMPLATE)
    rendered = template.render(generics=sorted_generics, nodes=sorted_nodes, base_protocols=base_protocols, sync=False)
    rendered_sync = template.render(
        generics=sorted_generics, nodes=sorted_nodes, base_protocols=base_protocols, sync=True
    )
    output_file = Path(out)
    output_file_sync = Path(output_file.stem + "_sync" + output_file.suffix)

    if out:
        write_to_file(output_file, rendered)
        write_to_file(output_file_sync, rendered_sync)
        console.print(f"Python protocols exported in {output_file} and {output_file_sync}")
    else:
        console.print(rendered)
        console.print(rendered_sync)


@app.command(name="version")
@catch_exception(console=console)
def version(_: str = CONFIG_PARAM):
    """Display the version of Infrahub and the version of the Python SDK in use."""

    client = initialize_client_sync()
    response = client.execute_graphql(query="query { InfrahubInfo { version }}")

    infrahub_version = response["InfrahubInfo"]["version"]
    console.print(f"Infrahub: v{infrahub_version}\nPython SDK: v{sdk_version}")
