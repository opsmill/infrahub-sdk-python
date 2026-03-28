"""Update command for the ``infrahub`` end-user CLI.

Fetches an existing object by kind and identifier, applies field changes
supplied via ``--set`` flags or a ``--file`` path, and saves the result.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer  # pyright: ignore[reportMissingImports]
from rich.console import Console  # pyright: ignore[reportMissingImports]

from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.parsers import parse_set_args, validate_set_fields
from infrahub_sdk.ctl.utils import catch_exception
from infrahub_sdk.spec.object import ObjectFile

if TYPE_CHECKING:
    from infrahub_sdk import InfrahubClient

console = Console()


@catch_exception(console=console)
async def update_command(
    kind: str = typer.Argument(..., help="Infrahub schema kind"),
    identifier: str = typer.Argument(..., help="Object ID or display name"),
    set_args: list[str] | None = typer.Option(None, "--set", help="Field value in key=value format"),
    file: Path | None = typer.Option(None, "--file", "-f", help="JSON or YAML file with update data"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    _: str = CONFIG_PARAM,
) -> None:
    """Update an existing object in Infrahub.

    Fetches the object identified by KIND and IDENTIFIER, applies the
    requested changes, and saves the updated object back to the server.

    Changes can be provided either as repeatable ``--set key=value``
    flags or via a ``--file`` pointing to a YAML/JSON object file.
    The two modes are mutually exclusive.

    Args:
        kind: Infrahub schema kind (e.g. ``InfraDevice``).
        identifier: Object UUID or human-readable display name.
        set_args: Repeatable key=value pairs for inline field updates.
        file: Path to a YAML or JSON object file with update data.
        branch: Target branch for the operation.
    """
    if set_args and file:
        raise typer.BadParameter("--set and --file are mutually exclusive.")

    if not set_args and not file:
        raise typer.BadParameter("Provide either --set or --file to specify update data.")

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
    validate_set_fields(data, schema.attribute_names, schema.relationship_names)

    node = await client.get(kind=kind, id=identifier)

    changes: list[tuple[str, object, str]] = []
    for key, new_value in data.items():
        if key in schema.attribute_names:
            attr = getattr(node, key)
            old_value = attr.value
            attr.value = new_value
            changes.append((key, old_value, new_value))
        elif key in schema.relationship_names:
            rel = getattr(node, key)
            old_id = getattr(rel, "id", None)
            await rel.fetch()  # type: ignore[union-attr]
            old_display = getattr(rel, "display_label", old_id)
            setattr(node, key, {"id": new_value})
            changes.append((key, old_display, new_value))

    await node.save()

    console.print(f"[green]Updated {kind} '{identifier}' successfully.")
    for field_name, old_val, new_val in changes:
        console.print(f"  {field_name}: {old_val} -> {new_val}")


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
