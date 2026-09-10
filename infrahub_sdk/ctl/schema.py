from __future__ import annotations

import ast
import asyncio
import difflib
import re
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import typer
import yaml
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..async_typer import AsyncTyper
from ..ctl.client import initialize_client
from ..ctl.utils import catch_exception, init_logging
from ..queries import SCHEMA_HASH_SYNC_STATUS
from ..schema import NodeSchemaAPI, SchemaWarning, validate_schema
from ..schema.generated.enums import AttributeKind
from ..yaml import SchemaFile
from .parameters import CONFIG_PARAM
from .schema_format import (
    DEFAULT_BACKFILL_ORDER_WEIGHT,
    FormatError,
    FormatOptions,
    format_schema_text,
    is_schema_document,
)
from .utils import load_yamlfile_from_disk_and_exit

SchemaContainer = Literal["nodes", "generics", "relationships"]

app = AsyncTyper()
console = Console()


class FormatOutcome(Enum):
    """Result of formatting a single schema file."""

    ERROR = "error"
    SKIPPED = "skipped"
    UNCHANGED = "unchanged"
    CHANGED = "changed"


@app.callback()
def callback() -> None:
    """Manage the schema in a remote Infrahub instance."""


def validate_schema_content_and_exit(schemas: list[SchemaFile]) -> None:
    """Report every offline contract violation and exit when at least one schema is invalid.

    Read-only fields are reported by the server on the load/check response, so only errors are
    rendered here to avoid warning about the same field twice.
    """
    has_error: bool = False
    for schema_file in schemas:
        result = validate_schema(schema=schema_file.payload)
        if result.valid:
            continue
        has_error = True
        console.print(f"[red]Schema not valid, found '{len(result.errors)}' error(s) in {schema_file.location}")
        for error in result.errors:
            console.print(f"  {escape(error.message)}")

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
        if _is_schema_level_error(error=error, loc_path=loc_path):
            _render_contract_violations(
                error=error, schema_index=int(loc_path[2]), schemas_data=schemas_data, output=out
            )
            continue
        if not valid_error_path(loc_path=loc_path):
            continue
        _render_schema_error(error=error, loc_path=loc_path, schemas_data=schemas_data, output=out)


# The server may report every write-contract violation of one schema as a single value error located on
# the schema itself. Its message then concatenates one `<field path>: <message> (received: <value>)` entry per
# violation, separated by `; `.
# `Value error, extensions.nodes[0].bogus: Unknown field (received: True); nodes[1].namespace: String should ...`
#  ^^^^^^^^^^^^^ _VALUE_ERROR_PREFIX
_VALUE_ERROR_PREFIX = "Value error, "
# `extensions.nodes[0].attributes[1].kind`
_FIELD_PATH = r"[A-Za-z_][\w.\[\]]*"
# `... (received: True); nodes[1].namespace: String ...`: the `; ` followed by the next `<field path>: `
_CONTRACT_VIOLATION_SEPARATOR = re.compile(rf"; (?={_FIELD_PATH}: )")
# `extensions.nodes[0].bogus: Unknown field, it is not part of the schema (received: True)`
#  ^field                     ^message                                   ^_RECEIVED_MARKER ^received
_RECEIVED_MARKER = " (received: "
_CONTRACT_VIOLATION = re.compile(
    rf"^(?P<field>{_FIELD_PATH}): (?P<message>.*?)(?: \(received: (?P<received>.*)\))?$", re.DOTALL
)
# `extensions.nodes[0].kind`: matches `extensions`, `nodes`, `[0]`, `kind` in turn
_FIELD_PATH_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _is_schema_level_error(error: dict[str, Any], loc_path: list[Any]) -> bool:
    return (
        error.get("type") == "value_error"
        and len(loc_path) == 3
        and loc_path[0] == "body"
        and loc_path[1] == "schemas"
        and isinstance(loc_path[2], int)
    )


def _split_contract_violations(message: str) -> list[str]:
    """Split the joined message into one entry per violation.

    A separator is only honoured when the text before it forms a complete violation: a received value is
    rendered with ``repr()`` and may itself contain ``; <word>: `` (e.g. a description), which must not be
    mistaken for the start of the next violation.
    """
    message = message.removeprefix(_VALUE_ERROR_PREFIX)
    violations: list[str] = []
    start = 0
    for separator in _CONTRACT_VIOLATION_SEPARATOR.finditer(message):
        candidate = message[start : separator.start()]
        if _is_complete_violation(text=candidate):
            violations.append(candidate)
            start = separator.end()
    if remainder := message[start:]:
        violations.append(remainder)
    return violations


def _is_complete_violation(text: str) -> bool:
    match = _CONTRACT_VIOLATION.match(text)
    if not match:
        return False
    if match["received"] is None:
        # A violation without a received value (e.g. a missing field) is whole unless the value was cut open.
        return _RECEIVED_MARKER not in text
    return _is_whole_received_value(received=match["received"])


def _is_whole_received_value(received: str) -> bool:
    # A false split can only land inside a quoted string, so a value without quotes is always whole.
    if "'" not in received and '"' not in received:
        return True
    try:
        ast.literal_eval(received)
    except (ValueError, SyntaxError):
        return False
    return True


def _parse_field_path(field: str) -> list[Any]:
    # `extensions.nodes[0].attributes[1].kind` -> ["extensions", "nodes", 0, "attributes", 1, "kind"]
    return [int(index) if index else name for name, index in _FIELD_PATH_SEGMENT.findall(field)]


def _parse_received_value(received: str) -> Any:
    try:
        return ast.literal_eval(received)
    except (ValueError, SyntaxError):
        return received


def _render_contract_violations(
    error: dict[str, Any], schema_index: int, schemas_data: list[SchemaFile], output: Console
) -> None:
    schema_label = (
        str(schemas_data[schema_index].location) if schema_index < len(schemas_data) else f"schema {schema_index}"
    )
    err_type = error.get("type", "unknown")

    for violation in _split_contract_violations(message=error.get("msg", "")):
        match = _CONTRACT_VIOLATION.match(violation)
        loc_path = ["body", "schemas", schema_index, *_parse_field_path(match["field"])] if match else []
        if not match or not valid_error_path(loc_path=loc_path):
            # The violation is not on a node (e.g. a root-level field): report it verbatim rather than drop it.
            output.print(f"  Schema: {schema_label} | {violation} ({err_type})", markup=False)
            continue
        field_error: dict[str, Any] = {"msg": match["message"], "type": err_type}
        if match["received"] is not None:
            # A missing field carries no received value: leave `input` out so none is displayed.
            field_error["input"] = _parse_received_value(match["received"])
        _render_schema_error(error=field_error, loc_path=loc_path, schemas_data=schemas_data, output=output)


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
    # No `input` key means nothing was submitted (a missing field): show no value rather than `(None)`.
    input_label = f" ({error['input']})" if "input" in error else ""
    err_msg = error.get("msg", "No error message")
    err_type = error.get("type", "unknown")

    if not tail:
        return

    if tail[0] in _NODE_ELEMENT_COLLECTIONS and len(tail) > 1:
        location = _element_location(node=node, tail=tail)
    else:
        # Error on a field of the node itself (e.g. `namespace`, `display_labels[0]`).
        location = _format_field_path(segments=tail)

    output.print(f"  Node: {node_label}{path_suffix} | {location}{input_label} | {err_msg} ({err_type})", markup=False)


_NODE_ELEMENT_COLLECTIONS = {"attributes", "relationships"}
_ATTRIBUTE_KINDS = frozenset(kind.value for kind in AttributeKind)


def _element_location(node: dict[str, Any], tail: list[Any]) -> str:
    """Locate an error inside an attribute or relationship: ["attributes", 0, "parameters", "regex"] -> "Attribute: serial | parameters.regex".

    The second segment is either the element index or, in older payloads, the failing field name.
    """
    collection, element = tail[0], tail[1]
    element_label = _resolve_attribute_label(error_data=node.get(collection, []), attribute=element)
    # Trim the trailing 's' so "attributes" → "Attribute" in the rendered label.
    location = f"{collection[:-1].title()}: {element_label}"
    field_segments = tail[2:]
    # Pydantic tags the union branch it validated an attribute against with its kind (`attributes[0].Text.name`).
    # That segment is not a submitted key and is dropped; any other segment is kept, CapitalCase or not.
    if collection == "attributes" and field_segments and field_segments[0] in _ATTRIBUTE_KINDS:
        field_segments = field_segments[1:]
    if field_path := _format_field_path(segments=field_segments):
        location = f"{location} | {field_path}"
    return location


def _format_field_path(segments: list[Any]) -> str:
    """Render location segments as a dotted path: ["choices", 1, "label"] -> "choices[1].label"."""
    parts = [f"[{segment}]" if isinstance(segment, int) else f".{segment}" for segment in segments]
    return "".join(parts).removeprefix(".")


def _resolve_attribute_label(error_data: list[Any], attribute: Any) -> str | None:
    if isinstance(attribute, str):
        for data in error_data:
            if isinstance(data, dict) and data.get(attribute) is not None:
                return data.get("name", None)
        return None
    if isinstance(attribute, int) and 0 <= attribute < len(error_data) and isinstance(error_data[attribute], dict):
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
    validate_schema_content_and_exit(schemas=schemas_data)

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
    validate_schema_content_and_exit(schemas=schemas_data)

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
        # A warning about a top-level key has no kind to attribute it to.
        kinds = f" [{', '.join(kind.display for kind in warning.kinds)}]" if warning.kinds else ""
        console.print(f"[yellow] {warning.type.value}: {escape(warning.message)}{escape(kinds)}")


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
        # markup=False keeps bracketed diff content (e.g. `[manufacturer, name]`)
        # literal, so colour is applied via style= rather than inline markup.
        if line.startswith("+") and not line.startswith("+++"):
            console.print(line, end="", markup=False, highlight=False, style="green")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(line, end="", markup=False, highlight=False, style="red")
        else:
            console.print(line, end="", markup=False, highlight=False)


def _format_one_schema_file(
    location: Path, entries: list[SchemaFile], check: bool, diff: bool, options: FormatOptions
) -> FormatOutcome:
    """Format a single schema file and report what happened.

    Args:
        location: Path of the file on disk.
        entries: SchemaFile entries parsed for this location (more than one means
            a genuine multi-document file, which is not supported).
        check: Report changes without writing.
        diff: Print a diff instead of writing.
        options: Opt-in transforms to apply.

    Returns:
        The :class:`FormatOutcome` for this file.

    """
    if len(entries) > 1:
        console.print(f"[yellow] Skipped {location}: multi-document files are not supported by format")
        return FormatOutcome.SKIPPED

    schema_file = entries[0]
    if not schema_file.valid or schema_file.content is None:
        console.print(f"[red] {location}: {schema_file.error_message or 'invalid file'}")
        return FormatOutcome.ERROR

    if not is_schema_document(schema_file.content):
        return FormatOutcome.SKIPPED

    original = location.read_text(encoding="utf-8")
    try:
        formatted = format_schema_text(original, options)
    except FormatError as exc:
        console.print(f"[red] {location}: {exc}")
        return FormatOutcome.ERROR

    if formatted == original:
        return FormatOutcome.UNCHANGED

    if diff:
        _print_schema_diff(location=location, original=original, formatted=formatted)
    elif check:
        console.print(f"[yellow] Would reformat {location}")
    else:
        location.write_text(formatted, encoding="utf-8")
        console.print(f"[green] Reformatted {location}")
    return FormatOutcome.CHANGED


@app.command(name="format")
@catch_exception(console=console)
def schema_format(
    schemas: list[Path],
    check: bool = typer.Option(False, "--check", help="Do not write files; exit 1 if any file would be reformatted."),
    diff: bool = typer.Option(False, "--diff", help="Print a diff of the changes instead of writing files."),
    strip_defaults: bool = typer.Option(
        False, "--strip-defaults", help="Remove attribute/relationship/node keys whose value equals the schema default."
    ),
    sort_by_order_weight: bool = typer.Option(
        False,
        "--sort-by-order-weight",
        help="Sort attributes and relationships by order_weight (items without one keep their order and go last).",
    ),
    backfill_order_weight: bool = typer.Option(
        False,
        "--backfill-order-weight",
        help=f"Give attributes/relationships that lack an order_weight the value {DEFAULT_BACKFILL_ORDER_WEIGHT}.",
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Format Infrahub schema files with a canonical key ordering.

    Reorders the keys within each node, generic, attribute, relationship and
    dropdown choice into a consistent, opinionated order so schema files read
    the same way and produce small diffs.

    Only your own nodes are formatted; nodes in Infrahub-reserved namespaces are
    left untouched. Comments, quoting, and inline (flow) sequences are preserved.

    By default the change is purely key ordering. The opt-in flags additionally
    change content: --strip-defaults drops redundant default values,
    --sort-by-order-weight reorders attributes/relationships, and
    --backfill-order-weight fills in a missing order_weight.

    \b
    Examples:
      infrahubctl schema format schemas/
      infrahubctl schema format schemas/dcim.yml --diff
      infrahubctl schema format schemas/ --check
      infrahubctl schema format schemas/ --strip-defaults --sort-by-order-weight
    """
    options = FormatOptions(
        strip_defaults=strip_defaults,
        sort_by_order_weight=sort_by_order_weight,
        backfill_order_weight=backfill_order_weight,
    )
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
        status = _format_one_schema_file(location=location, entries=entries, check=check, diff=diff, options=options)
        if status is FormatOutcome.ERROR:
            has_error = True
        elif status is FormatOutcome.UNCHANGED:
            unchanged += 1
        elif status is FormatOutcome.CHANGED:
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
