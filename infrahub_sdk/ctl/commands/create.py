"""Command implementation for ``infrahub create``.

Creates a new object in Infrahub either from inline ``--set`` key=value
arguments or from a JSON/YAML object file specified via ``--file``.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.parsers import parse_set_args, validate_set_fields
from infrahub_sdk.ctl.utils import catch_exception
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

    Supports two mutually exclusive modes: inline field assignment via
    repeatable ``--set key=value`` options, or bulk creation from a
    JSON/YAML object file via ``--file``.

    Args:
        kind: The Infrahub schema kind to create (e.g. ``InfraDevice``).
        set_args: Repeatable ``key=value`` pairs for inline field assignment.
        file: Path to a JSON or YAML object file.
        branch: Target branch for the operation.
        _: Configuration file parameter (handled by callback).
    """
    if set_args and file:
        raise typer.BadParameter("--set and --file are mutually exclusive. Use one or the other.")
    if not set_args and not file:
        raise typer.BadParameter("Provide either --set key=value pairs or --file <path>.")

    client = initialize_client(branch=branch)

    if file:
        files = ObjectFile.load_from_disk(paths=[file])
        for obj_file in files:
            await obj_file.validate_format(client=client, branch=branch)
            await obj_file.process(client=client, branch=branch)
            object_count = len(obj_file.spec.data)
            console.print(f"[green]Created {object_count} objects of kind {obj_file.spec.kind}")
    else:
        data = parse_set_args(set_args)  # type: ignore[arg-type]
        schema = await client.schema.get(kind=kind, branch=branch)
        validate_set_fields(data, schema.attribute_names, schema.relationship_names)
        node = await client.create(kind=kind, data=data, branch=branch)
        await node.save(allow_upsert=True)
        console.print(f"[green]Created {kind} '{node.display_label}' (id: {node.id})")
