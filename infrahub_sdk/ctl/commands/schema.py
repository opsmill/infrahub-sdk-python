"""``infrahub schema`` subcommand group -- explore the Infrahub schema.

Provides ``list`` and ``show`` subcommands for inspecting schema kinds
and their attributes and relationships.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.utils import catch_exception
from infrahub_sdk.schema import NodeSchemaAPI

app = AsyncTyper()
console = Console()


@app.callback()
def callback() -> None:
    """Explore the Infrahub schema."""


@app.command(name="list")
@catch_exception(console=console)
async def schema_list(
    filter_text: str | None = typer.Option(None, "--filter", help="Filter kinds by name substring"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    _: str = CONFIG_PARAM,
) -> None:
    """List all available schema kinds.

    Fetches the full schema from the Infrahub instance and displays a
    table of ``NodeSchemaAPI`` entries.  Use ``--filter`` to narrow results
    by a case-insensitive substring match on the kind name.

    Args:
        filter_text: Optional substring to filter kind names.
        branch: Target branch name.
        _: Configuration file path (handled by callback).
    """
    client = initialize_client(branch=branch)
    schemas = await client.schema.all(branch=branch)

    items = list(schemas.values())
    if filter_text:
        items = [s for s in items if filter_text.lower() in s.kind.lower()]

    items = [s for s in items if isinstance(s, NodeSchemaAPI)]
    items.sort(key=lambda s: s.kind)

    table = Table(title="Schema Kinds")
    table.add_column("Namespace")
    table.add_column("Name")
    table.add_column("Kind")
    table.add_column("Description")

    for schema in items:
        table.add_row(
            schema.namespace,
            schema.name,
            schema.kind,
            schema.description or "",
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

    Args:
        kind: Infrahub schema kind (e.g. ``InfraDevice``).
        branch: Target branch name.
        _: Configuration file path (handled by callback).
    """
    client = initialize_client(branch=branch)
    schema = await client.schema.get(kind=kind, branch=branch)

    console.print(f"\n[bold]{schema.kind}[/bold]")
    if schema.description:
        console.print(f"  {schema.description}")
    console.print(f"  Namespace: {schema.namespace}")
    console.print(f"  Display Labels: {schema.display_labels or 'N/A'}")
    console.print(f"  Human Friendly ID: {schema.human_friendly_id or 'N/A'}")

    if schema.attributes:
        attr_table = Table(title="Attributes")
        attr_table.add_column("Name")
        attr_table.add_column("Type")
        attr_table.add_column("Required")
        attr_table.add_column("Default")
        attr_table.add_column("Description")

        for attr in schema.attributes:
            attr_table.add_row(
                attr.name,
                str(attr.kind),
                "Yes" if not attr.optional else "No",
                str(attr.default_value) if attr.default_value is not None else "",
                attr.description or "",
            )
        console.print(attr_table)

    if schema.relationships:
        rel_table = Table(title="Relationships")
        rel_table.add_column("Name")
        rel_table.add_column("Peer")
        rel_table.add_column("Cardinality")
        rel_table.add_column("Optional")

        for rel in schema.relationships:
            rel_table.add_row(
                rel.name,
                rel.peer,
                rel.cardinality,
                "Yes" if rel.optional else "No",
            )
        console.print(rel_table)
