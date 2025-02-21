from __future__ import annotations

from asyncio import run as aiorun
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..ctl.client import initialize_client
from ..transfer.exceptions import TransferError
from ..transfer.importer.json import LineDelimitedJSONImporter
from ..transfer.schema_sorter import InfrahubSchemaTopologicalSorter
from .parameters import CONFIG_PARAM


def local_directory() -> Path:
    # We use a function here to avoid failure when generating the documentation due to directory name
    return Path().resolve()


def load(
    directory: Path = typer.Option(local_directory, help="Directory path of exported data"),
    continue_on_error: bool = typer.Option(
        False, help="Allow exceptions during loading and display them when complete"
    ),
    quiet: bool = typer.Option(False, help="No console output"),
    _: str = CONFIG_PARAM,
    branch: str = typer.Option(None, help="Branch from which to export"),
    concurrent: Optional[int] = typer.Option(
        None,
        help="Maximum number of requests to execute at the same time.",
        envvar="INFRAHUB_MAX_CONCURRENT_EXECUTION",
    ),
    timeout: int = typer.Option(60, help="Timeout in sec", envvar="INFRAHUB_TIMEOUT"),
) -> None:
    """Import nodes and their relationships into the database."""
    console = Console()

    client = initialize_client(
        branch=branch, timeout=timeout, max_concurrent_execution=concurrent, retry_on_failure=True
    )

    importer = LineDelimitedJSONImporter(
        client,
        InfrahubSchemaTopologicalSorter(),
        continue_on_error=continue_on_error,
        console=Console() if not quiet else None,
    )
    try:
        aiorun(importer.import_data(import_directory=directory, branch=branch))
    except TransferError as exc:
        console.print(f"[red]{exc}")
        raise typer.Exit(1)
