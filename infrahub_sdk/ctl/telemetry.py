from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import orjson
import typer
from rich.console import Console
from rich.table import Table

from ..async_typer import AsyncTyper
from .client import initialize_client
from .parameters import CONFIG_PARAM
from .utils import catch_exception

app = AsyncTyper()
console = Console()

EXPORT_PAGE_SIZE = 1000


@app.command(name="list")
@catch_exception(console=console)
async def list_snapshots(
    start_date: datetime | None = typer.Option(
        None, help="Start date filter (ISO 8601)", formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]
    ),
    end_date: datetime | None = typer.Option(
        None, help="End date filter (ISO 8601)", formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]
    ),
    limit: int = typer.Option(50, help="Maximum number of results"),
    _: str = CONFIG_PARAM,
) -> None:
    """List telemetry snapshots with summary information."""
    client = initialize_client()

    params: dict[str, str | int] = {"limit": limit}
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()

    url = f"{client.address}/api/telemetry/snapshots?{urlencode(params)}"
    response = await client._get(url=url, timeout=client.default_timeout)
    response.raise_for_status()
    data = response.json()

    snapshots = data.get("snapshots", [])
    if not snapshots:
        console.print("No telemetry snapshots found.")
        return

    table = Table()
    table.add_column("Date")
    table.add_column("Version")
    table.add_column("Type")
    table.add_column("Deployment")
    table.add_column("Remote Status")

    for snap in snapshots:
        table.add_row(
            snap.get("created_at", ""),
            snap.get("infrahub_version", ""),
            snap.get("kind", ""),
            snap.get("deployment_id", ""),
            snap.get("remote_send_status", ""),
        )

    console.print(table)
    console.print(f"Showing {len(snapshots)} of {data.get('count', len(snapshots))} total snapshots")


@app.command(name="export")
@catch_exception(console=console)
async def export_snapshots(
    output: str = typer.Option("telemetry-export.json", help="Output file path"),
    start_date: datetime | None = typer.Option(
        None, help="Start date filter (ISO 8601)", formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]
    ),
    end_date: datetime | None = typer.Option(
        None, help="End date filter (ISO 8601)", formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Export telemetry snapshots to a JSON file.

    Pages through the API automatically so that all matching snapshots are exported,
    not just the first page.
    """
    client = initialize_client()

    base_params: dict[str, str | int] = {}
    if start_date:
        base_params["start_date"] = start_date.isoformat()
    if end_date:
        base_params["end_date"] = end_date.isoformat()

    snapshots: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None

    while True:
        params: dict[str, str | int] = {**base_params, "limit": EXPORT_PAGE_SIZE, "offset": offset}
        url = f"{client.address}/api/telemetry/snapshots?{urlencode(params)}"
        response = await client._get(url=url, timeout=client.default_timeout)
        response.raise_for_status()
        data = response.json()

        page: list[dict[str, Any]] = data.get("snapshots", [])
        snapshots.extend(page)

        if total is None:
            total = int(data.get("count", len(page)))

        if len(page) < EXPORT_PAGE_SIZE or len(snapshots) >= total:
            break

        offset += EXPORT_PAGE_SIZE

    if not snapshots:
        console.print("No telemetry snapshots found.")
        raise typer.Exit(code=2)

    output_path = Path(output)
    output_path.write_text(orjson.dumps(snapshots, option=orjson.OPT_INDENT_2).decode(), encoding="utf-8")
    console.print(f"Exported {len(snapshots)} snapshots to {output_path}")
