import logging
from pathlib import Path

import typer
from rich.console import Console

from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.utils import catch_exception, init_logging
from infrahub_sdk.spec.object import ObjectFile

from .parameters import CONFIG_PARAM
from .utils import load_yamlfile_from_disk_and_exit

app = AsyncTyper()
console = Console()


@app.callback()
def callback() -> None:
    """
    Manage objects in a remote Infrahub instance.
    """


@app.command()
@catch_exception(console=console)
async def load(
    paths: list[Path],
    debug: bool = False,
    branch: str = typer.Option("main", help="Branch on which to load the objects."),
    _: str = CONFIG_PARAM,
) -> None:
    """Load one or multiple objects files into Infrahub."""

    init_logging(debug=debug)

    logging.getLogger("infrahub_sdk").setLevel(logging.INFO)

    files = load_yamlfile_from_disk_and_exit(paths=paths, file_type=ObjectFile, console=console)
    client = await initialize_client()

    for file in files:
        file.validate_content()
        schema = await client.schema.get(kind=file.spec.kind, branch=branch)

        for item in file.spec.data:
            await file.spec.create_node(client=client, schema=schema, data=item, branch=branch)
