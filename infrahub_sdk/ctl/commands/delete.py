"""``infrahub delete`` command -- delete an Infrahub object by ID or display name.

Prompts for confirmation before deletion unless ``--yes`` is passed.
"""

from __future__ import annotations

import typer
from rich.console import Console

from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.utils import catch_exception

console = Console()


@catch_exception(console=console)
async def delete_command(
    kind: str = typer.Argument(..., help="Infrahub schema kind"),
    identifier: str = typer.Argument(..., help="Object ID or display name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    _: str = CONFIG_PARAM,
) -> None:
    """Delete an Infrahub object.

    Fetches the object identified by *identifier* (UUID or display name) and
    deletes it.  Unless ``--yes`` is provided, the user is prompted for
    confirmation before the deletion is executed.

    Args:
        kind: Infrahub schema kind (e.g. ``InfraDevice``).
        identifier: UUID or display name of the object to delete.
        yes: When ``True``, skip the interactive confirmation prompt.
        branch: Target branch name.
        _: Configuration file path (handled by callback).
    """
    client = initialize_client(branch=branch)
    node = await client.get(kind=kind, id=identifier)

    if not yes:
        typer.confirm(f"Delete {kind} '{node.display_label}'?", abort=True)

    await node.delete()
    console.print(f"[green]Deleted {kind} '{node.display_label}' (id: {node.id})")
