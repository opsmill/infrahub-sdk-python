import logging
from pathlib import Path

import typer
from rich.console import Console

from ..async_typer import AsyncTyper
from ..ctl.client import initialize_client
from ..ctl.utils import catch_exception, init_logging
from ..spec.menu import MenuFile
from .parameters import CONFIG_PARAM
from .utils import load_yamlfile_from_disk_and_exit

app = AsyncTyper()
console = Console()


@app.callback()
def callback() -> None:
    """
    Manage the menu in a remote Infrahub instance.
    """


@app.command()
@catch_exception(console=console)
async def load(
    menus: list[Path],
    debug: bool = False,
    branch: str = typer.Option(None, help="Branch on which to load the menu."),
    _: str = CONFIG_PARAM,
) -> None:
    """Load one or multiple menu files into Infrahub."""

    init_logging(debug=debug)

    logging.getLogger("infrahub_sdk").setLevel(logging.INFO)

    files = load_yamlfile_from_disk_and_exit(paths=menus, file_type=MenuFile, console=console)
    client = initialize_client()

    for file in files:
        file.validate_content()
        schema = await client.schema.get(kind=file.spec.kind, branch=branch)

        for idx, item in enumerate(file.spec.data):
            await file.spec.create_node(
                client=client,
                schema=schema,
                data=item,
                branch=branch,
                default_schema_kind=file.spec.kind,
                context={"list_index": idx},
            )
