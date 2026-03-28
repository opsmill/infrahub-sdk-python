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
from infrahub_sdk.ctl.commands.utils import resolve_node, resolve_relationship_values
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
    identifier: str = typer.Argument(..., help="UUID, name, or HFID (use / for multi-part, e.g. Cisco/NX-OS)"),
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
        console.print("[dim]Note: KIND and IDENTIFIER are ignored in --file mode; "
                      "the file defines target objects.[/dim]")
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

    node = await resolve_node(client, kind, identifier, schema=schema, branch=branch)

    resolved_data = await resolve_relationship_values(client, data, schema, branch=branch)

    changes: list[tuple[str, object, object]] = []
    for key, new_value in data.items():
        if key in schema.attribute_names:
            attr = getattr(node, key)
            old_value = attr.value
            attr.value = new_value
            changes.append((key, old_value, new_value))
        elif key in schema.relationship_names:
            rel = getattr(node, key)
            old_id = getattr(rel, "id", None)
            old_display = getattr(rel, "display_label", old_id)
            resolved = resolved_data[key]
            new_id = resolved.get("id") if isinstance(resolved, dict) else resolved
            if old_id != new_id:
                setattr(node, key, resolved)
                changes.append((key, old_display, new_value))

    actual_changes = [(f, o, n) for f, o, n in changes if str(o) != str(n)]

    if not actual_changes:
        console.print(f"[yellow]No changes — {kind} '{identifier}' already has the requested values.")
        return

    await node.save()

    console.print(f"[green]Updated {kind} '{identifier}' successfully.")
    for field_name, old_val, new_val in actual_changes:
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
