"""``infrahub get`` command -- query and display Infrahub objects.

Supports both list mode (all objects of a kind) and detail mode (a single
object by ID or display name).  Output is auto-detected as ``table`` for
interactive terminals and ``json`` when piped, but can be overridden with
``--output``.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console

from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.formatters import OutputFormat, detect_output_format, get_formatter
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.parsers import parse_filter_args
from infrahub_sdk.ctl.utils import catch_exception

console = Console()


@catch_exception(console=console)
async def get_command(
    kind: str = typer.Argument(..., help="Infrahub schema kind to query"),
    identifier: str | None = typer.Argument(None, help="Object ID or display name for detail view"),
    filter_args: list[str] | None = typer.Option(None, "--filter", help="Filter in attr__value=x format"),
    output: OutputFormat | None = typer.Option(None, "--output", "-o", help="Output format"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    limit: int | None = typer.Option(None, "--limit", help="Maximum results"),
    offset: int | None = typer.Option(None, "--offset", help="Skip first N results"),
    _: str = CONFIG_PARAM,
) -> None:
    """Query and display Infrahub objects.

    When IDENTIFIER is omitted, lists all objects of the given KIND.
    When IDENTIFIER is provided, displays a single object in detail view.
    """
    client = initialize_client(branch=branch)
    schema = await client.schema.get(kind=kind, branch=branch)

    fmt = output or detect_output_format()
    formatter = get_formatter(fmt)

    if identifier is not None:
        node = await client.get(kind=kind, id=identifier)
        result = formatter.format_detail(node, schema)
    else:
        filters: dict[str, Any] = parse_filter_args(filter_args or [])
        nodes = await client.filters(
            kind=kind,
            **filters,
            offset=offset,
            limit=limit,
            prefetch_relationships=True,
        )
        result = formatter.format_list(nodes, schema)

    if fmt == OutputFormat.TABLE:
        console.print(result, highlight=False)
    else:
        typer.echo(result)
