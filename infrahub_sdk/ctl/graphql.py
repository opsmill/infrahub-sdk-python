from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import Optional

import typer
from ariadne_codegen.client_generators.package import PackageGenerator, get_package_generator
from ariadne_codegen.exceptions import ParsingError
from ariadne_codegen.plugins.explorer import get_plugins_types
from ariadne_codegen.plugins.manager import PluginManager
from ariadne_codegen.schema import (
    filter_fragments_definitions,
    filter_operations_definitions,
    get_graphql_schema_from_path,
)
from ariadne_codegen.settings import ClientSettings, CommentsStrategy
from ariadne_codegen.utils import ast_to_str
from graphql import DefinitionNode, GraphQLSchema, NoUnusedFragmentsRule, parse, specified_rules, validate
from rich.console import Console

from ..async_typer import AsyncTyper
from ..ctl.client import initialize_client
from ..ctl.utils import catch_exception
from ..graphql.utils import insert_fragments_inline, remove_fragment_import
from .parameters import CONFIG_PARAM

app = AsyncTyper()
console = Console()

ARIADNE_PLUGINS = [
    "infrahub_sdk.graphql.plugin.PydanticBaseModelPlugin",
    "infrahub_sdk.graphql.plugin.FutureAnnotationPlugin",
    "infrahub_sdk.graphql.plugin.StandardTypeHintPlugin",
]


def find_gql_files(query_path: Path) -> list[Path]:
    """
    Find all files with .gql extension in the specified directory.

    Args:
        query_path: Path to the directory to search for .gql files

    Returns:
        List of Path objects for all .gql files found
    """
    if not query_path.exists():
        raise FileNotFoundError(f"File or directory not found: {query_path}")

    if not query_path.is_dir() and query_path.is_file():
        return [query_path]

    return list(query_path.glob("**/*.gql"))


def get_graphql_query(queries_path: Path, schema: GraphQLSchema) -> tuple[DefinitionNode, ...]:
    """Get GraphQL queries definitions from a single GraphQL file."""

    if not queries_path.exists():
        raise FileNotFoundError(f"File not found: {queries_path}")
    if not queries_path.is_file():
        raise ValueError(f"{queries_path} is not a file")

    queries_str = queries_path.read_text(encoding="utf-8")
    queries_ast = parse(queries_str)
    validation_errors = validate(
        schema=schema,
        document_ast=queries_ast,
        rules=[r for r in specified_rules if r is not NoUnusedFragmentsRule],
    )
    if validation_errors:
        raise ValueError("\n\n".join(error.message for error in validation_errors))
    return queries_ast.definitions


def generate_result_types(directory: Path, package: PackageGenerator, fragment: ast.Module) -> None:
    for file_name, module in package._result_types_files.items():
        file_path = directory / file_name

        insert_fragments_inline(module, fragment)
        remove_fragment_import(module)

        code = package._add_comments_to_code(ast_to_str(module), package.queries_source)
        if package.plugin_manager:
            code = package.plugin_manager.generate_result_types_code(code)
        file_path.write_text(code)
        package._generated_files.append(file_path.name)


@app.callback()
def callback() -> None:
    """
    Various GraphQL related commands.
    """


@app.command()
@catch_exception(console=console)
async def export_schema(
    destination: Path = typer.Option("schema.graphql", help="Path to the GraphQL schema file."),
    _: str = CONFIG_PARAM,
) -> None:
    """Export the GraphQL schema to a file."""

    client = initialize_client()
    schema_text = await client.schema.get_graphql_schema()

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(schema_text)
    console.print(f"[green]Schema exported to {destination}")


@app.command()
@catch_exception(console=console)
async def generate_return_types(
    query: Optional[Path] = typer.Argument(
        None, help="Location of the GraphQL query file(s). Defaults to current directory if not specified."
    ),
    schema: Path = typer.Option("schema.graphql", help="Path to the GraphQL schema file."),
    _: str = CONFIG_PARAM,
) -> None:
    """Create Pydantic Models for GraphQL query return types"""

    query = Path.cwd() if query is None else query

    # Load the GraphQL schema
    if not schema.exists():
        raise FileNotFoundError(f"GraphQL Schema file not found: {schema}")
    graphql_schema = get_graphql_schema_from_path(schema_path=str(schema))

    # Initialize the plugin manager
    plugin_manager = PluginManager(
        schema=graphql_schema,
        plugins_types=get_plugins_types(plugins_strs=ARIADNE_PLUGINS),
    )

    # Find the GraphQL files and organize them by directory
    gql_files = find_gql_files(query)
    gql_per_directory: dict[Path, list[Path]] = defaultdict(list)
    for gql_file in gql_files:
        gql_per_directory[gql_file.parent].append(gql_file)

    # Generate the Pydantic Models for the GraphQL queries
    for directory, gql_files in gql_per_directory.items():
        for gql_file in gql_files:
            try:
                definitions = get_graphql_query(queries_path=gql_file, schema=graphql_schema)
            except ValueError as exc:
                console.print(f"[red]Error generating result types for {gql_file}: {exc}")
                continue
            queries = filter_operations_definitions(definitions)
            fragments = filter_fragments_definitions(definitions)

            package_generator = get_package_generator(
                schema=graphql_schema,
                fragments=fragments,
                settings=ClientSettings(
                    schema_path=str(schema),
                    target_package_name=directory.name,
                    queries_path=str(directory),
                    include_comments=CommentsStrategy.NONE,
                ),
                plugin_manager=plugin_manager,
            )

            parsing_failed = False
            try:
                for query_operation in queries:
                    package_generator.add_operation(query_operation)
            except ParsingError as exc:
                console.print(f"[red]Unable to process {gql_file.name}: {exc}")
                parsing_failed = True

            if parsing_failed:
                continue

            module_fragment = package_generator.fragments_generator.generate()

            generate_result_types(directory=directory, package=package_generator, fragment=module_fragment)

            for file_name in package_generator._result_types_files.keys():
                console.print(f"[green]Generated {file_name} in {directory}")
