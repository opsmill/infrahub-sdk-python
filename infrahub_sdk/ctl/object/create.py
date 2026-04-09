"""Command implementation for ``infrahub create``.

Creates a new object in Infrahub either from inline ``--set`` key=value
arguments or from a JSON/YAML object file specified via ``--file``.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import typer
from rich.console import Console

from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.object.utils import derive_identifier, prepare_relationship_data, resolve_node
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.parsers import parse_set_args, validate_set_fields
from infrahub_sdk.ctl.utils import catch_exception
from infrahub_sdk.exceptions import NodeNotFoundError
from infrahub_sdk.spec.object import ObjectFile

console = Console()


@catch_exception(console=console)
async def create_command(
    kind: str = typer.Argument(..., help="Infrahub schema kind to create"),
    set_args: list[str] | None = typer.Option(None, "--set", help="Field value in key=value format"),
    file: Path | None = typer.Option(None, "--file", "-f", help="JSON or YAML file with object data"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    _: str = CONFIG_PARAM,
) -> None:
    """Create a new object in Infrahub.

    Provide field values with repeatable --set flags or supply a
    JSON/YAML object file via --file. The two modes are mutually exclusive.

    \b
    Examples:
      infrahubctl object create InfraDevice --set name=spine01 --set status=active
      infrahubctl object create InfraDevice --set name=spine01 --set location=DC1
      infrahubctl object create InfraDevice --file devices.yml
    """
    if set_args and file:
        console.print("[red]Error: --set and --file are mutually exclusive.")
        raise typer.Exit(code=1)
    if not set_args and not file:
        console.print("[red]Error: provide --set key=value or --file <path>.")
        console.print("Example: infrahubctl object create MyKind --set name=foo --set status=active")
        raise typer.Exit(code=1)

    client = initialize_client(branch=branch)

    if file:
        files = ObjectFile.load_from_disk(paths=[file])

        # Validate all files before processing any to avoid partial application
        for obj_file in files:
            if obj_file.spec.kind != kind:
                console.print(f"[red]Error: file kind '{obj_file.spec.kind}' does not match positional kind '{kind}'.")
                raise typer.Exit(code=1)
            await obj_file.validate_format(client=client, branch=branch)

        for obj_file in files:
            await obj_file.process(client=client, branch=branch)
            object_count = len(obj_file.spec.data)
            console.print(f"[green]Created {object_count} objects of kind {obj_file.spec.kind}")
    elif set_args:
        data = parse_set_args(set_args)
        schema = await client.schema.get(kind=kind, branch=branch)
        validate_set_fields(data, schema.attribute_names, schema.relationship_names)
        data = prepare_relationship_data(data, schema)

        # Check if node already exists to distinguish create from upsert
        existing = None
        identifier_value = derive_identifier(data, schema)
        if identifier_value is not None:
            with contextlib.suppress(NodeNotFoundError):
                existing = await resolve_node(client, kind, identifier_value, schema=schema, branch=branch)

        node = await client.create(kind=kind, data=data, branch=branch)
        await node.save(allow_upsert=True)
        label = node.display_label or identifier_value or node.id

        if existing:
            console.print(f"[yellow]Updated {kind} '{label}' (id: {node.id}) — already existed")
        else:
            console.print(f"[green]Created {kind} '{label}' (id: {node.id})")
