from __future__ import annotations

import asyncio
import difflib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ..async_typer import AsyncTyper
from ..ctl.client import initialize_client
from ..ctl.utils import catch_exception, init_logging
from ..queries import SCHEMA_HASH_SYNC_STATUS
from ..schema import NodeSchemaAPI, SchemaWarning
from ..yaml import SchemaFile
from .parameters import CONFIG_PARAM
from .schema_format import FormatError, format_schema_text, is_schema_document
from .utils import load_yamlfile_from_disk_and_exit

if TYPE_CHECKING:
    from .. import InfrahubClient

SchemaContainer = Literal["nodes", "generics", "relationships"]

app = AsyncTyper()
console = Console()


@app.callback()
def callback() -> None:
    """Manage the schema in a remote Infrahub instance."""


def validate_schema_content_and_exit(client: InfrahubClient, schemas: list[SchemaFile]) -> None:
    has_error: bool = False
    for schema_file in schemas:
        try:
            client.schema.validate(data=schema_file.payload)
        except ValidationError as exc:
            console.print(f"[red]Schema not valid, found '{len(exc.errors())}' error(s) in {schema_file.location}")
            has_error = True
            for error in exc.errors():
                loc_str = [str(item) for item in error["loc"]]
                console.print(f"  '{'/'.join(loc_str)}' | {error['msg']} ({error['type']})")

    if has_error:
        raise typer.Exit(1)


def display_schema_load_errors(
    response: dict[str, Any], schemas_data: list[SchemaFile], output: Console | None = None
) -> None:
    out = output or console
    out.print("[red]Unable to load the schema:")
    if "detail" not in response:
        handle_non_detail_errors(response=response, output=out)
        return

    for error in response["detail"]:
        loc_path = error.get("loc", [])
        if not valid_error_path(loc_path=loc_path):
            continue
        _render_schema_error(error=error, loc_path=loc_path, schemas_data=schemas_data, output=out)


def _render_schema_error(
    error: dict[str, Any], loc_path: list[Any], schemas_data: list[SchemaFile], output: Console
) -> None:
    # Two layout shapes for loc_path. tail is the part after the node index.
    # Top-level: body / schemas / <si> / (nodes|generics) / <ni> / [<subtype> / <attr>]
    # Extensions: body / schemas / <si> / extensions / (nodes|generics|relationships) / <ni> / [<subtype> / <attr>]
    schema_index = int(loc_path[2])
    is_extension = loc_path[3] == "extensions"
    if is_extension:
        container = loc_path[4]
        node_index = int(loc_path[5])
        tail = loc_path[6:]
    else:
        container = loc_path[3]
        node_index = int(loc_path[4])
        tail = loc_path[5:]

    node = get_node(
        schemas_data=schemas_data,
        schema_index=schema_index,
        node_index=node_index,
        container=container,
        is_extension=is_extension,
    )

    if not node:
        output.print("Node data not found.")
        return

    # Extensions reference an existing node by `kind`; new top-level nodes are identified by `namespace+name`.
    node_label = (
        (node.get("kind") or node.get("name") or "")
        if is_extension
        else f"{node.get('namespace', None)}{node.get('name', None)}"
    )
    path_suffix = f" (extensions/{container})" if is_extension else ""
    input_str = error.get("input")
    err_msg = error.get("msg", "No error message")
    err_type = error.get("type", "unknown")

    if len(tail) == 1:
        # Error on a direct field of the node (e.g. `name`, `namespace`).
        loc_type = tail[0]
        error_message = f"{loc_type} ({input_str}) | {err_msg} ({err_type})"
    elif len(tail) > 1:
        # Error nested inside a collection (e.g. attributes[2].kind, relationships[0].peer).
        # loc_type is the collection name; attribute is either its index or the failing field name.
        loc_type = tail[0]
        attribute = tail[1]
        input_label = _resolve_attribute_label(error_data=node.get(loc_type, []), attribute=attribute)
        # Trim the trailing 's' so "attributes" → "Attribute" in the rendered label.
        error_message = f"{loc_type[:-1].title()}: {input_label} ({input_str}) | {err_msg} ({err_type})"
    else:
        return

    output.print(f"  Node: {node_label}{path_suffix} | {error_message}", markup=False)


def _resolve_attribute_label(error_data: list[dict[str, Any]], attribute: Any) -> str | None:
    if isinstance(attribute, str):
        for data in error_data:
            if data.get(attribute) is not None:
                return data.get("name", None)
        return None
    if isinstance(attribute, int) and 0 <= attribute < len(error_data):
        return error_data[attribute].get("name", None)
    return None


def handle_non_detail_errors(response: dict[str, Any], output: Console | None = None) -> None:
    out = output or console
    if "error" in response:
        out.print(f"  {response.get('error')}")
    elif "errors" in response:
        for error in response["errors"]:
            out.print(f"  {error.get('message')}")
    else:
        out.print(f"  '{response}'")


def valid_error_path(loc_path: list[Any]) -> bool:
    if len(loc_path) < 6 or loc_path[0] != "body" or loc_path[1] != "schemas" or not isinstance(loc_path[2], int):
        return False
    if loc_path[3] == "extensions":
        return (
            len(loc_path) >= 7
            and loc_path[4] in {"nodes", "generics", "relationships"}
            and isinstance(loc_path[5], int)
        )
    return loc_path[3] in {"nodes", "generics"} and isinstance(loc_path[4], int)


def get_node(
    schemas_data: list[SchemaFile],
    schema_index: int,
    node_index: int,
    container: SchemaContainer = "nodes",
    is_extension: bool = False,
) -> dict | None:
    if schema_index >= len(schemas_data):
        return None
    payload = schemas_data[schema_index].payload
    items = payload.get("extensions", {}).get(container, []) if is_extension else payload.get(container, [])
    if node_index < len(items):
        return items[node_index]
    return None


@app.command(short_help="Load one or multiple schema files into Infrahub.")
@catch_exception(console=console)
async def load(
    schemas: list[Path],
    debug: bool = False,
    branch: str = typer.Option(None, help="Branch on which to load the schema."),
    wait: int = typer.Option(0, help="Time in seconds to wait until the schema has converged across all workers"),
    _: str = CONFIG_PARAM,
) -> None:
    """Load one or multiple schema files into Infrahub."""
    init_logging(debug=debug)

    schemas_data = load_yamlfile_from_disk_and_exit(paths=schemas, file_type=SchemaFile, console=console)
    schema_definition = "schema" if len(schemas_data) == 1 else "schemas"
    client = initialize_client()
    validate_schema_content_and_exit(client=client, schemas=schemas_data)

    start_time = time.time()
    response = await client.schema.load(schemas=[item.payload for item in schemas_data], branch=branch)
    loading_time = time.time() - start_time

    if response.errors:
        display_schema_load_errors(response=response.errors, schemas_data=schemas_data)
        raise typer.Exit(1)

    if response.schema_updated:
        for schema_file in schemas_data:
            console.print(f"[green] schema '{schema_file.location}' loaded successfully")
    else:
        console.print("[green] The schema in Infrahub was already up to date, no changes were required")

    console.print(f"[green] {len(schemas_data)} {schema_definition} processed in {loading_time:.3f} seconds.")

    _display_schema_warnings(console=console, warnings=response.warnings)

    if response.schema_updated and wait:
        waited = 0
        continue_waiting = True
        while continue_waiting:
            status = await client.execute_graphql(query=SCHEMA_HASH_SYNC_STATUS, branch_name=branch)
            if status["InfrahubStatus"]["summary"]["schema_hash_synced"]:
                console.print("[green] Schema updated on all workers.")
                continue_waiting = False
            else:
                if waited >= wait:
                    console.print("[red] Schema is still not in sync after the specified waiting time")
                    raise typer.Exit(1)
                console.print("[yellow] Waiting for schema to sync across all workers")
                waited += 1
                await asyncio.sleep(delay=1)


@app.command(short_help="Check if schema files are valid and their impact on Infrahub.")
@catch_exception(console=console)
async def check(
    schemas: list[Path],
    debug: bool = False,
    branch: str = typer.Option(None, help="Branch on which to check the schema."),
    _: str = CONFIG_PARAM,
) -> None:
    """Check if schema files are valid and what would be the impact of loading them with Infrahub."""
    init_logging(debug=debug)

    schemas_data = load_yamlfile_from_disk_and_exit(paths=schemas, file_type=SchemaFile, console=console)
    client = initialize_client()
    validate_schema_content_and_exit(client=client, schemas=schemas_data)

    success, response = await client.schema.check(schemas=[item.payload for item in schemas_data], branch=branch)

    if not success or not response:
        display_schema_load_errors(response=response or {}, schemas_data=schemas_data)
        return

    for schema_file in schemas_data:
        console.print(f"[green] schema '{schema_file.location}' is Valid!")

    warnings = response.pop("warnings", [])
    schema_warnings = [SchemaWarning.model_validate(warning) for warning in warnings]
    _display_schema_warnings(console=console, warnings=schema_warnings)
    if response == {"diff": {"added": {}, "changed": {}, "removed": {}}}:
        print("No diff")
    else:
        print(yaml.safe_dump(data=response, indent=4))


def _display_schema_warnings(console: Console, warnings: list[SchemaWarning]) -> None:
    for warning in warnings:
        console.print(
            f"[yellow] {warning.type.value}: {warning.message} [{', '.join([kind.display for kind in warning.kinds])}]"
        )


def _default_export_directory() -> Path:
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    return Path(f"infrahub-schema-export-{timestamp}")


@app.command()
@catch_exception(console=console)
async def export(
    directory: Path = typer.Option(_default_export_directory, help="Directory path to store schema files"),
    branch: str = typer.Option(None, help="Branch from which to export the schema"),
    namespaces: list[str] = typer.Option([], help="Namespace(s) to export (default: all user-defined)"),
    debug: bool = False,
    _: str = CONFIG_PARAM,
) -> None:
    """Export the schema from Infrahub as YAML files, one per namespace."""
    init_logging(debug=debug)

    client = initialize_client()
    user_schemas = await client.schema.export(
        branch=branch,
        namespaces=namespaces or None,
    )

    if not user_schemas.namespaces:
        console.print("[yellow]No user-defined schema found to export.")
        return

    directory.mkdir(parents=True, exist_ok=True)

    for ns, data in sorted(user_schemas.namespaces.items()):
        payload: dict[str, Any] = {"version": "1.0"}
        if data.generics:
            payload["generics"] = data.generics
        if data.nodes:
            payload["nodes"] = data.nodes

        output_file = directory / f"{ns.lower()}.yml"
        output_file.write_text(
            yaml.dump(payload, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        console.print(f"[green] Exported namespace '{ns}' to {output_file}")

    console.print(f"[green] Schema exported to {directory}")


@app.command(name="list")
@catch_exception(console=console)
async def schema_list(
    filter_text: str | None = typer.Option(None, "--filter", help="Filter kinds by name"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    _: str = CONFIG_PARAM,
) -> None:
    """List all available schema kinds.

    Displays a table of all node schema entries. Use --filter to narrow
    results by a case-insensitive match on the kind name.

    \b
    Examples:
      infrahubctl schema list
      infrahubctl schema list --filter Device
    """
    client = initialize_client(branch=branch)
    schemas = await client.schema.all(branch=branch)

    items = [s for s in schemas.values() if isinstance(s, NodeSchemaAPI)]
    if filter_text:
        items = [s for s in items if filter_text.lower() in s.kind.lower()]
    items.sort(key=lambda s: s.kind)

    table = Table(title="Schema Kinds")
    table.add_column("Namespace")
    table.add_column("Name")
    table.add_column("Kind")
    table.add_column("Description")

    for schema_item in items:
        table.add_row(
            schema_item.namespace,
            schema_item.name,
            schema_item.kind,
            schema_item.description or "",
        )

    console.print(table)


@app.command(name="show")
@catch_exception(console=console)
async def schema_show(
    kind: str = typer.Argument(..., help="Schema kind to display"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    _: str = CONFIG_PARAM,
) -> None:
    """Show details for a specific schema kind.

    Displays metadata, attributes, and relationships for the requested
    schema kind in a human-readable format.

    \b
    Examples:
      infrahubctl schema show InfraDevice
    """
    client = initialize_client(branch=branch)
    node_schema = await client.schema.get(kind=kind, branch=branch)

    console.print(f"\n[bold]{node_schema.kind}[/bold]")
    if node_schema.description:
        console.print(f"  {node_schema.description}")
    console.print(f"  Namespace: {node_schema.namespace}")
    console.print(f"  Display Labels: {node_schema.display_labels or 'N/A'}")
    console.print(f"  Human Friendly ID: {node_schema.human_friendly_id or 'N/A'}")

    if node_schema.attributes:
        attr_table = Table(title="Attributes")
        attr_table.add_column("Name")
        attr_table.add_column("Type")
        attr_table.add_column("Required")
        attr_table.add_column("Default")
        attr_table.add_column("Description")

        for attr in node_schema.attributes:
            attr_table.add_row(
                attr.name,
                str(attr.kind),
                "Yes" if not attr.optional else "No",
                str(attr.default_value) if attr.default_value is not None else "",
                attr.description or "",
            )
        console.print(attr_table)

    if node_schema.relationships:
        rel_table = Table(title="Relationships")
        rel_table.add_column("Name")
        rel_table.add_column("Peer")
        rel_table.add_column("Cardinality")
        rel_table.add_column("Optional")

        for rel in node_schema.relationships:
            rel_table.add_row(
                rel.name,
                rel.peer,
                rel.cardinality,
                "Yes" if rel.optional else "No",
            )
        console.print(rel_table)


def _print_schema_diff(location: Path, original: str, formatted: str) -> None:
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        formatted.splitlines(keepends=True),
        fromfile=f"{location} (current)",
        tofile=f"{location} (formatted)",
    )
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line}", end="", markup=False, highlight=False)
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line}", end="", markup=False, highlight=False)
        else:
            console.print(line, end="", markup=False, highlight=False)


def _format_one_schema_file(location: Path, entries: list[SchemaFile], check: bool, diff: bool) -> str:
    """Format a single schema file and report what happened.

    Args:
        location: Path of the file on disk.
        entries: SchemaFile entries parsed for this location (more than one means
            a genuine multi-document file, which is not supported).
        check: Report changes without writing.
        diff: Print a diff instead of writing.

    Returns:
        One of ``"error"``, ``"skipped"``, ``"unchanged"`` or ``"changed"``.
    """
    if len(entries) > 1:
        console.print(f"[yellow] Skipped {location}: multi-document files are not supported by format")
        return "skipped"

    schema_file = entries[0]
    if not schema_file.valid or schema_file.content is None:
        console.print(f"[red] {location}: {schema_file.error_message or 'invalid file'}")
        return "error"

    if not is_schema_document(schema_file.content):
        return "skipped"

    original = location.read_text(encoding="utf-8")
    try:
        formatted = format_schema_text(original)
    except FormatError as exc:
        console.print(f"[red] {location}: {exc}")
        return "error"

    if formatted == original:
        return "unchanged"

    if diff:
        _print_schema_diff(location=location, original=original, formatted=formatted)
    elif check:
        console.print(f"[yellow] Would reformat {location}")
    else:
        location.write_text(formatted, encoding="utf-8")
        console.print(f"[green] Reformatted {location}")
    return "changed"


@app.command(name="format")
@catch_exception(console=console)
def schema_format(
    schemas: list[Path],
    check: bool = typer.Option(False, "--check", help="Do not write files; exit 1 if any file would be reformatted."),
    diff: bool = typer.Option(False, "--diff", help="Print a diff of the changes instead of writing files."),
    _: str = CONFIG_PARAM,
) -> None:
    """Format Infrahub schema files with a canonical key ordering.

    Reorders the keys within each node, generic, attribute, relationship and
    dropdown choice into a consistent, opinionated order so schema files read
    the same way and produce small diffs. List items (the attributes and
    relationships themselves) are never reordered.

    Only your own nodes are formatted; nodes in Infrahub-reserved namespaces are
    left untouched. Comments, quoting, and inline (flow) sequences are preserved.

    \b
    Examples:
      infrahubctl schema format schemas/
      infrahubctl schema format schemas/dcim.yml --diff
      infrahubctl schema format schemas/ --check
    """
    schema_files = SchemaFile.load_from_disk(paths=schemas)

    # A genuine multi-document file yields several SchemaFile entries for the
    # same location. The per-file ``multiple_documents`` flag is unreliable
    # (it is set from a naive `---` substring count that also matches `---`
    # inside comments), so group by location and count real documents instead.
    entries_by_location: dict[Path, list[SchemaFile]] = {}
    for schema_file in schema_files:
        entries_by_location.setdefault(schema_file.location, []).append(schema_file)

    reformatted = 0
    unchanged = 0
    would_change = 0
    has_error = False

    for location, entries in entries_by_location.items():
        status = _format_one_schema_file(location=location, entries=entries, check=check, diff=diff)
        if status == "error":
            has_error = True
        elif status == "unchanged":
            unchanged += 1
        elif status == "changed":
            if check or diff:
                would_change += 1
            else:
                reformatted += 1

    if check or diff:
        console.print(f"\n[bold]{would_change} file(s) would be reformatted, {unchanged} unchanged.")
    else:
        console.print(f"\n[bold]{reformatted} file(s) reformatted, {unchanged} unchanged.")

    if has_error or (check and would_change):
        raise typer.Exit(1)
