"""Telemetry CLI commands for exporting and managing telemetry data.

This module provides CLI commands to export locally stored telemetry data
for airgapped environments and to list available telemetry files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..async_typer import AsyncTyper
from .client import initialize_client
from .parameters import CONFIG_PARAM
from .utils import catch_exception

app = AsyncTyper()
console = Console()


@app.callback()
def callback() -> None:
    """Manage telemetry data export and operations.

    Export locally stored telemetry data for airgapped environments
    or list available telemetry files.
    """


@app.command(name="export")
@catch_exception(console=console)
async def export_telemetry(
    output: Path = typer.Option(
        Path("telemetry-export.json"),
        "--output",
        "-o",
        help="Output file path for the export",
    ),
    from_date: str | None = typer.Option(
        None,
        "--from",
        help="Start date for export range (YYYY-MM-DD)",
    ),
    to_date: str | None = typer.Option(
        None,
        "--to",
        help="End date for export range (YYYY-MM-DD)",
    ),
    export_all: bool = typer.Option(
        False,
        "--all",
        help="Export all available telemetry data",
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Export telemetry data from Infrahub for airgapped transfer.

    This command exports locally stored telemetry data into a format
    suitable for manual transfer to OpsMill for airgapped environments.

    Examples:

        # Export last 30 days
        infrahubctl telemetry export --from 2025-01-01 --to 2025-01-31

        # Export all available data
        infrahubctl telemetry export --all

        # Export to specific file
        infrahubctl telemetry export --all --output my-export.json
    """
    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    client = initialize_client()

    # Build query parameters for the REST API
    params: dict[str, Any] = {}
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date
    if export_all:
        params["all"] = "true"

    # Query the REST API for telemetry export
    url = f"{client.address}/api/telemetry/export"
    response = await client._get(url=url, params=params, timeout=client.default_timeout)

    if response.status_code != 200:
        console.print(f"[red]Error: {response.text}")
        raise typer.Exit(1)

    export_data = response.json()

    # Write to file (using Path.write_text for non-blocking file operations)
    output.write_text(json.dumps(export_data, indent=2, default=str), encoding="utf-8")

    # Show summary
    snapshots = export_data.get("snapshots", [])
    license_info = export_data.get("license", {})

    table = Table(title="Export Summary", show_header=False, box=None)
    table.add_column(justify="left", style="cyan")
    table.add_column(justify="right", style="green")

    table.add_row("Customer", license_info.get("customer_name", "Unknown"))
    table.add_row("Product Tier", license_info.get("product_tier", "Unknown"))
    table.add_row("Snapshots", str(len(snapshots)))

    if snapshots:
        first_date = snapshots[0].get("date", "N/A")
        last_date = snapshots[-1].get("date", "N/A")
        table.add_row("Date Range", f"{first_date} to {last_date}")

    table.add_row("Output File", str(output))

    console.print()
    console.print(table)
    console.print()
    console.print(Panel(f"[green]Export complete: {output}[/green]", border_style="green"))


@app.command(name="list")
@catch_exception(console=console)
async def list_telemetry(
    _: str = CONFIG_PARAM,
) -> None:
    """List available local telemetry files.

    Shows all telemetry files stored locally on the Infrahub instance,
    including their dates and sizes.
    """
    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    client = initialize_client()

    url = f"{client.address}/api/telemetry/list"
    response = await client._get(url=url, timeout=client.default_timeout)

    if response.status_code != 200:
        console.print(f"[red]Error: {response.text}")
        raise typer.Exit(1)

    files = response.json().get("files", [])

    if not files:
        console.print("[yellow]No telemetry files found[/yellow]")
        return

    table = Table(title="Local Telemetry Files")
    table.add_column("Date", style="cyan")
    table.add_column("Filename", style="green")
    table.add_column("Size", style="yellow", justify="right")

    for f in files:
        table.add_row(f.get("date", "N/A"), f.get("filename", "N/A"), f.get("size", "N/A"))

    console.print()
    console.print(table)
    console.print()


@app.command(name="status")
@catch_exception(console=console)
async def telemetry_status(
    _: str = CONFIG_PARAM,
) -> None:
    """Show telemetry configuration and status.

    Displays the current telemetry configuration including whether
    telemetry is enabled, the storage path, and retention settings.
    """
    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    client = initialize_client()

    url = f"{client.address}/api/telemetry/status"
    response = await client._get(url=url, timeout=client.default_timeout)

    if response.status_code != 200:
        console.print(f"[red]Error: {response.text}")
        raise typer.Exit(1)

    status = response.json()

    table = Table(title="Telemetry Status", show_header=False, box=None)
    table.add_column(justify="left", style="cyan")
    table.add_column(justify="right")

    enabled = status.get("enabled", False)
    table.add_row("Telemetry Enabled", "[green]Yes[/green]" if enabled else "[red]No[/red]")
    table.add_row("Storage Path", status.get("storage_path", "N/A"))
    table.add_row("Retention Days", str(status.get("retention_days", "N/A")))
    table.add_row("Files Count", str(status.get("files_count", 0)))

    if status.get("latest_file"):
        table.add_row("Latest File", status.get("latest_file", "N/A"))

    if status.get("license"):
        license_info = status["license"]
        table.add_row("", "")  # Spacer
        table.add_row("[bold]License Information[/bold]", "")
        table.add_row("Customer Name", license_info.get("customer_name", "N/A"))
        table.add_row("Product Tier", license_info.get("product_tier", "N/A"))
        table.add_row("License Valid", "[green]Yes[/green]" if license_info.get("valid") else "[red]No[/red]")

    console.print()
    console.print(table)
    console.print()
