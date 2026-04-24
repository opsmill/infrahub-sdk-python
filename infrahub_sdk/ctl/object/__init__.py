import logging
from pathlib import Path

import typer
from rich.console import Console

from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl.client import initialize_client
from infrahub_sdk.ctl.object.create import create_command
from infrahub_sdk.ctl.object.delete import delete_command
from infrahub_sdk.ctl.object.get import get_command
from infrahub_sdk.ctl.object.update import update_command
from infrahub_sdk.ctl.parameters import CONFIG_PARAM
from infrahub_sdk.ctl.utils import (
    catch_exception,
    display_object_validate_format_error,
    display_object_validate_format_success,
    init_logging,
    load_yamlfile_from_disk_and_exit,
)
from infrahub_sdk.exceptions import ObjectValidationError, ValidationError
from infrahub_sdk.spec.object import ObjectFile

app = AsyncTyper()
console = Console()

app.command(name="get")(get_command)
app.command(name="create")(create_command)
app.command(name="update")(update_command)
app.command(name="delete")(delete_command)


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
