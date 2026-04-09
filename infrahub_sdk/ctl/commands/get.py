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
from infrahub_sdk.ctl.commands.utils import resolve_node
from infrahub_sdk.ctl.formatters import OutputFormat, detect_output_format, get_formatter
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.parsers import parse_filter_args
from infrahub_sdk.ctl.utils import catch_exception

EXIT_CODE_NO_RESULTS = 80

console = Console()
console_stderr = Console(stderr=True)


@catch_exception(console=console)
async def get_command(
    kind: str = typer.Argument(..., help="Infrahub schema kind to query"),
    identifier: str | None = typer.Argument(
        None, help="UUID, name, or HFID (use / for multi-part, for example: Cisco/NX-OS)"
    ),
    filter_args: list[str] | None = typer.Option(None, "--filter", help="Filter in attr__value=x format"),
    output: OutputFormat | None = typer.Option(None, "--output", "-o", help="Output format"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Target branch"),
    limit: int | None = typer.Option(None, "--limit", help="Maximum results"),
    offset: int | None = typer.Option(None, "--offset", help="Skip first N results"),
    all_columns: bool = typer.Option(False, "--all-columns", help="Show all columns including empty ones"),
    _: str = CONFIG_PARAM,
) -> None:
    """Query and display Infrahub objects.

    When IDENTIFIER is omitted the command lists all objects of the given
    KIND. When IDENTIFIER is provided it displays a single object in
    detail view. Empty columns are hidden by default (use --all-columns).

    \b
    Examples:
      infrahubctl object get InfraDevice
      infrahubctl object get InfraDevice spine01
      infrahubctl object get InfraDevice --filter name__value=spine01
      infrahubctl object get InfraDevice --output json
      infrahubctl object get InfraDevice --output yaml > backup.yml

    Exit codes: 0 = results found, 1 = error (including not found in detail
    mode), 80 = list query succeeded but returned zero objects.
    """
    client = initialize_client(branch=branch)
    schema = await client.schema.get(kind=kind, branch=branch)

    fmt = output or detect_output_format()
    formatter = get_formatter(fmt)

    if identifier is not None:
        node = await resolve_node(client, kind, identifier, schema=schema, branch=branch)
        result = formatter.format_detail(node, schema)
        if fmt == OutputFormat.TABLE:
            console.print(result, highlight=False)
        else:
            typer.echo(result)
        return

    filters: dict[str, Any] = parse_filter_args(filter_args or [])
    nodes = await client.filters(
        kind=kind,
        **filters,
        branch=branch,
        offset=offset,
        limit=limit,
        prefetch_relationships=True,
    )

    count = len(nodes)
    result = formatter.format_list(nodes, schema, show_all_columns=all_columns)

    if fmt == OutputFormat.TABLE:
        console.print(result, highlight=False)
        console.print(f"\n{count} object(s) found.", style="dim")
    else:
        typer.echo(result)

    if count == 0:
        console_stderr.print(f"No objects of kind {kind} found.", style="yellow")
        raise typer.Exit(code=EXIT_CODE_NO_RESULTS)
