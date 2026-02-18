from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console

from ..async_typer import AsyncTyper
from ..constants import RESTRICTED_NAMESPACES
from ..ctl.client import initialize_client
from ..ctl.utils import catch_exception, init_logging
from ..queries import SCHEMA_HASH_SYNC_STATUS
from ..schema import GenericSchemaAPI, NodeSchemaAPI, ProfileSchemaAPI, SchemaWarning, TemplateSchemaAPI
from ..yaml import SchemaFile
from .parameters import CONFIG_PARAM
from .utils import load_yamlfile_from_disk_and_exit

if TYPE_CHECKING:
    from .. import InfrahubClient

app = AsyncTyper()
console = Console()


@app.callback()
def callback() -> None:
    """
    Manage the schema in a remote Infrahub instance.
    """


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


def display_schema_load_errors(response: dict[str, Any], schemas_data: list[SchemaFile]) -> None:
    console.print("[red]Unable to load the schema:")
    if "detail" not in response:
        handle_non_detail_errors(response=response)
        return

    for error in response["detail"]:
        loc_path = error.get("loc", [])
        if not valid_error_path(loc_path=loc_path):
            continue

        # if the len of the path is equal to 6, the error is at the root of the object
        # if the len of the path is higher than 6, the error is in an attribute or a relationships
        schema_index = int(loc_path[2])
        node_index = int(loc_path[4])
        node = get_node(schemas_data=schemas_data, schema_index=schema_index, node_index=node_index)

        if not node:
            console.print("Node data not found.")
            continue

        if len(loc_path) == 6:
            loc_type = loc_path[-1]
            input_str = error.get("input", None)
            error_message = f"{loc_type} ({input_str}) | {error['msg']} ({error['type']})"
            console.print(
                f"  Node: {node.get('namespace', None)}{node.get('name', None)} | {error_message}", markup=False
            )

        elif len(loc_path) > 6:
            loc_type = loc_path[5]
            error_data = node[loc_type]
            attribute = loc_path[6]

            if isinstance(attribute, str):
                input_label = None
                for data in error_data:
                    if data.get(attribute) is not None:
                        input_label = data.get("name", None)
                        break
            else:
                input_label = error_data[attribute].get("name", None)

            input_str = error.get("input", None)
            error_message = f"{loc_type[:-1].title()}: {input_label} ({input_str}) | {error['msg']} ({error['type']})"
            console.print(
                f"  Node: {node.get('namespace', None)}{node.get('name', None)} | {error_message}", markup=False
            )


def handle_non_detail_errors(response: dict[str, Any]) -> None:
    if "error" in response:
        console.print(f"  {response.get('error')}")
    elif "errors" in response:
        for error in response["errors"]:
            console.print(f"  {error.get('message')}")
    else:
        console.print(f"  '{response}'")


def valid_error_path(loc_path: list[Any]) -> bool:
    return len(loc_path) >= 6 and loc_path[0] == "body" and loc_path[1] == "schemas"


def get_node(schemas_data: list[SchemaFile], schema_index: int, node_index: int) -> dict | None:
    if schema_index < len(schemas_data) and node_index < len(schemas_data[schema_index].payload["nodes"]):
        return schemas_data[schema_index].payload["nodes"][node_index]
    return None


@app.command()
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


@app.command()
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


def _default_export_directory() -> str:
    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    return f"infrahub-schema-export-{timestamp}"


_SCHEMA_EXPORT_EXCLUDE: set[str] = {"hash", "hierarchy", "used_by", "id", "state"}
# branch is inherited from the node and need not be repeated on each field
_FIELD_EXPORT_EXCLUDE: set[str] = {"inherited", "allow_override", "hierarchical", "id", "state", "branch"}

# Attribute field values that match schema loading defaults — omitted for cleaner output
_ATTR_EXPORT_DEFAULTS: dict[str, Any] = {
    "read_only": False,
}

# Relationship field values that match schema loading defaults — omitted for cleaner output
_REL_EXPORT_DEFAULTS: dict[str, Any] = {
    "direction": "bidirectional",
    "on_delete": "no-action",
    "cardinality": "many",
    "optional": True,
    "min_count": 0,
    "max_count": 0,
    "read_only": False,
}

# Relationship kinds that Infrahub generates automatically — never user-defined
_AUTO_GENERATED_REL_KINDS: frozenset[str] = frozenset({"Group", "Profile", "Hierarchy"})


def _schema_to_export_dict(schema: NodeSchemaAPI | GenericSchemaAPI) -> dict[str, Any]:
    """Convert an API schema object to an export-ready dict (omits API-internal fields)."""
    data = schema.model_dump(exclude=_SCHEMA_EXPORT_EXCLUDE, exclude_none=True)

    # Pop attrs/rels so they can be re-inserted last for better readability
    data.pop("attributes", None)
    data.pop("relationships", None)

    # Generics with Hierarchy relationships were defined with `hierarchical: true`.
    # Restore that flag and drop the auto-generated rels so the schema round-trips cleanly.
    if isinstance(schema, GenericSchemaAPI) and any(
        rel.kind == "Hierarchy" for rel in schema.relationships if not rel.inherited
    ):
        data["hierarchical"] = True

    attributes = [
        {
            k: v
            for k, v in attr.model_dump(exclude=_FIELD_EXPORT_EXCLUDE, exclude_none=True).items()
            if k not in _ATTR_EXPORT_DEFAULTS or v != _ATTR_EXPORT_DEFAULTS[k]
        }
        for attr in schema.attributes
        if not attr.inherited
    ]
    if attributes:
        data["attributes"] = attributes

    relationships = [
        {
            k: v
            for k, v in rel.model_dump(exclude=_FIELD_EXPORT_EXCLUDE, exclude_none=True).items()
            if k not in _REL_EXPORT_DEFAULTS or v != _REL_EXPORT_DEFAULTS[k]
        }
        for rel in schema.relationships
        if not rel.inherited and rel.kind not in _AUTO_GENERATED_REL_KINDS
    ]
    if relationships:
        data["relationships"] = relationships

    return data


@app.command()
@catch_exception(console=console)
async def export(
    directory: Path = typer.Option(_default_export_directory, help="Directory path to store schema files"),
    branch: str = typer.Option(None, help="Branch from which to export the schema"),
    namespace: list[str] = typer.Option([], help="Namespace(s) to export (default: all user-defined)"),
    debug: bool = False,
    _: str = CONFIG_PARAM,
) -> None:
    """Export the schema from Infrahub as YAML files, one per namespace."""
    init_logging(debug=debug)

    client = initialize_client()
    schema_nodes = await client.schema.fetch(branch=branch or client.default_branch)

    user_schemas: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for schema in schema_nodes.values():
        if isinstance(schema, (ProfileSchemaAPI, TemplateSchemaAPI)):
            continue
        if schema.namespace in RESTRICTED_NAMESPACES:
            continue
        if namespace and schema.namespace not in namespace:
            continue
        ns = schema.namespace
        user_schemas.setdefault(ns, {"nodes": [], "generics": []})
        schema_dict = _schema_to_export_dict(schema)
        if isinstance(schema, GenericSchemaAPI):
            user_schemas[ns]["generics"].append(schema_dict)
        else:
            user_schemas[ns]["nodes"].append(schema_dict)

    if not user_schemas:
        console.print("[yellow]No user-defined schema found to export.")
        return

    directory.mkdir(parents=True, exist_ok=True)

    for ns, data in sorted(user_schemas.items()):
        payload: dict[str, Any] = {"version": "1.0"}
        if data["nodes"]:
            payload["nodes"] = data["nodes"]
        if data["generics"]:
            payload["generics"] = data["generics"]

        output_file = directory / f"{ns.lower()}.yml"
        output_file.write_text(
            yaml.dump(payload, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        console.print(f"[green] Exported namespace '{ns}' to {output_file}")

    console.print(f"[green] Schema exported to {directory}")
