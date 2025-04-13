import logging
from pathlib import Path

import typer
from rich.console import Console

from ..async_typer import AsyncTyper
from ..ctl.client import initialize_client
from ..ctl.utils import catch_exception, init_logging
from ..exceptions import ObjectValidationError, ValidationError
from ..spec.object import ObjectFile
from .parameters import CONFIG_PARAM
from .utils import (
    display_object_validate_format_error,
    display_object_validate_format_success,
    load_yamlfile_from_disk_and_exit,
)

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
    branch: str = typer.Option(None, help="Branch on which to load the objects."),
    _: str = CONFIG_PARAM,
) -> None:
    """Load one or multiple objects files into Infrahub."""

    init_logging(debug=debug)

    logging.getLogger("infrahub_sdk").setLevel(logging.INFO)

    files = load_yamlfile_from_disk_and_exit(paths=paths, file_type=ObjectFile, console=console)
    client = initialize_client()

    has_errors = False

    for file in files:
        try:
            await file.validate_format(client=client, branch=branch)
        except ValidationError as exc:
            has_errors = True
            display_object_validate_format_error(file=file, error=exc, console=console)

    if has_errors:
        raise typer.Exit(1)

    for file in files:
        try:
            await file.process(client=client, branch=branch)
        except ObjectValidationError as exc:
            has_errors = True
            console.print(f"[red] {exc!s}")

    if has_errors:
        raise typer.Exit(1)


@app.command()
@catch_exception(console=console)
async def validate(
    paths: list[Path],
    debug: bool = False,
    branch: str = typer.Option(None, help="Branch on which to validate the objects."),
    _: str = CONFIG_PARAM,
) -> None:
    """Validate one or multiple objects files."""

    init_logging(debug=debug)

    logging.getLogger("infrahub_sdk").setLevel(logging.INFO)

    files = load_yamlfile_from_disk_and_exit(paths=paths, file_type=ObjectFile, console=console)
    client = initialize_client()

    has_errors = False
    for file in files:
        try:
            await file.validate_format(client=client, branch=branch)
            display_object_validate_format_success(file=file, console=console)
        except ValidationError as exc:
            has_errors = True
            display_object_validate_format_error(file=file, error=exc, console=console)

    if has_errors:
        raise typer.Exit(1)
