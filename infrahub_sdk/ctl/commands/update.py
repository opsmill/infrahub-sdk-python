"""Update command for the ``infrahub`` end-user CLI.

Fetches an existing object by kind and identifier, applies field changes
supplied via ``--set`` flags or a ``--file`` path, and saves the result.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.commands.utils import prepare_relationship_data, resolve_node
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.parsers import parse_set_args, validate_set_fields
from infrahub_sdk.ctl.utils import catch_exception
from infrahub_sdk.node.relationship import RelatedNode
from infrahub_sdk.schema.main import RelationshipCardinality
from infrahub_sdk.spec.object import ObjectFile

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient
    from infrahub_sdk.node import InfrahubNode
    from infrahub_sdk.schema import MainSchemaTypesAPI

console = Console()


@catch_exception(console=console)
async def update_command(
    kind: str = typer.Argument(..., help="Infrahub schema kind"),
    identifier: str = typer.Argument(..., help="UUID, name, or HFID (use / for multi-part, for example: Cisco/NX-OS)"),
    set_args: list[str] | None = typer.Option(None, "--set", help="Field value in key=value format"),
    file: Path | None = typer.Option(None, "--file", "-f", help="JSON or YAML file with update data"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    _: str = CONFIG_PARAM,
) -> None:
    """Update an existing object in Infrahub.

    Fetches the object by KIND and IDENTIFIER, applies the requested
    changes, and saves back to the server. Use --set or --file.

    \b
    Examples:
      infrahubctl update InfraDevice spine01 --set status=active
      infrahubctl update InfraDevice spine01 --set location=DC1
      infrahubctl update InfraDevice spine01 --file updates.yml
    """
    if set_args and file:
        console.print("[red]Error: --set and --file are mutually exclusive.")
        raise typer.Exit(code=1)

    if not set_args and not file:
        console.print("[red]Error: provide --set key=value or --file <path>.")
        console.print("Example: infrahubctl update MyKind my-node --set field=value")
        raise typer.Exit(code=1)

    client = initialize_client(branch=branch)

    if set_args:
        await _update_with_set_args(
            client=client,
            kind=kind,
            identifier=identifier,
            set_args=set_args,
            branch=branch,
        )
    elif file:
        console.print(
            "[dim]Note: KIND and IDENTIFIER are ignored in --file mode; the file defines target objects.[/dim]"
        )
        await _update_with_file(
            client=client,
            file=file,
            branch=branch,
        )


async def _update_with_set_args(
    client: InfrahubClient,
    kind: str,
    identifier: str,
    set_args: list[str],
    branch: str | None,
) -> None:
    """Apply inline --set key=value updates to an existing object.

    Parses the set arguments, validates them against the schema, fetches
    the target node, applies changes, and saves.

    Args:
        client: Initialised async Infrahub client.
        kind: Infrahub schema kind.
        identifier: Object UUID or display name.
        set_args: List of "key=value" strings.
        branch: Optional target branch.
    """
    data = parse_set_args(set_args)
    schema = await client.schema.get(kind=kind, branch=branch)
    attr_names = schema.attribute_names
    rel_names = schema.relationship_names
    validate_set_fields(data, attr_names, rel_names)

    node = await resolve_node(client, kind, identifier, schema=schema, branch=branch)

    prepared = prepare_relationship_data(data, schema)

    # Detect changes before mutating so no-op check is accurate
    attr_changes: list[tuple[str, object, object]] = []
    rel_changes: list[str] = []
    for key, new_value in data.items():
        if key in attr_names:
            old_value = getattr(node, key).value
            if str(old_value) != str(new_value):
                attr_changes.append((key, old_value, new_value))
        elif key in rel_names:
            if _relationship_changed(node, key, prepared[key], schema):
                rel_changes.append(key)

    if not attr_changes and not rel_changes:
        console.print(f"[yellow]No changes — {kind} '{identifier}' already has the requested values.")
        return

    for key, _old, new_val in attr_changes:
        getattr(node, key).value = new_val

    for key in rel_changes:
        _apply_relationship(node, key, prepared[key], schema)

    await node.save()

    console.print(f"[green]Updated {kind} '{identifier}' successfully.")
    for field_name, old_val, new_val in attr_changes:
        console.print(f"  {field_name}: {old_val} -> {new_val}")
    for key in rel_changes:
        console.print(f"  {key}: -> {data[key]}")


async def _update_with_file(
    client: InfrahubClient,
    file: Path,
    branch: str | None,
) -> None:
    """Apply updates from a YAML/JSON object file.

    Loads the file, validates its format against the server schema,
    then processes it to apply the changes.

    Args:
        client: Initialised async Infrahub client.
        file: Path to the YAML or JSON object file.
        branch: Optional target branch.
    """
    files = ObjectFile.load_from_disk(paths=[file])
    for obj_file in files:
        await obj_file.validate_format(client=client, branch=branch)
        await obj_file.process(client=client, branch=branch)

    console.print(f"[green]Processed update from file '{file}' successfully.")


def _relationship_changed(
    node: InfrahubNode,
    key: str,
    new_value: object,
    schema: MainSchemaTypesAPI,
) -> bool:
    """Check whether a relationship value actually differs from the node's current state."""
    rel_schema = schema.get_relationship(key)
    if rel_schema.cardinality == RelationshipCardinality.ONE:
        rel = getattr(node, key, None)
        if rel is None or not getattr(rel, "initialized", False):
            return True
        if getattr(rel, "id", None) is not None and isinstance(new_value, str):
            return rel.id != new_value
        old_hfid = getattr(rel, "hfid", None)
        if old_hfid is not None and isinstance(new_value, list):
            return list(old_hfid) != new_value
        return True
    # cardinality many — always treat as changed since the CLI can't express
    # the full current set for comparison
    return True


def _apply_relationship(
    node: InfrahubNode,
    key: str,
    new_value: object,
    schema: MainSchemaTypesAPI,
) -> None:
    """Set a relationship value using the proper InfrahubNode API.

    For cardinality-one, ``__setattr__`` correctly creates a ``RelatedNode``.
    For cardinality-many, directly manipulate the ``RelationshipManager``
    to avoid overwriting it via ``object.__setattr__``.
    """
    rel_schema = schema.get_relationship(key)
    if rel_schema.cardinality == RelationshipCardinality.ONE:
        setattr(node, key, new_value)
        return

    # Cardinality many: access the RelationshipManager from internal storage
    many_data: dict[str, object] = getattr(node, "_relationship_cardinality_many_data", {})
    rel_manager = many_data.get(key)
    if rel_manager is None or not hasattr(rel_manager, "peers"):
        return

    client = node._client
    branch: str = node._branch

    rel_manager.peers.clear()
    items = new_value if isinstance(new_value, list) and new_value and isinstance(new_value[0], list) else [new_value]
    for item in items:
        peer = RelatedNode(
            name=rel_schema.name,
            branch=branch,
            client=client,
            schema=rel_schema,
            data=item,
        )
        rel_manager.peers.append(peer)
