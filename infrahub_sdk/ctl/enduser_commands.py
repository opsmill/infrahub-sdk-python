"""Main command registration for the ``infrahub`` end-user CLI.

Registers top-level commands (get, create, update, delete) and the ``schema``
subcommand group. A ``--version`` flag is available on the root command.
"""

from __future__ import annotations

import typer

from infrahub_sdk import __version__ as sdk_version
from infrahub_sdk.async_typer import AsyncTyper
from infrahub_sdk.ctl.commands.create import create_command
from infrahub_sdk.ctl.commands.delete import delete_command
from infrahub_sdk.ctl.commands.get import get_command
from infrahub_sdk.ctl.commands.schema import app as schema_app
from infrahub_sdk.ctl.commands.update import update_command

app = AsyncTyper(pretty_exceptions_show_locals=False)


def _version_callback(value: bool) -> None:
    """Print the SDK version and exit.

    Args:
        value: Whether the ``--version`` flag was passed.

    Raises:
        typer.Exit: Always raised after printing the version.
    """
    if value:
        typer.echo(f"infrahub v{sdk_version}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Show the SDK version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Infrahub CLI -- interact with an Infrahub instance from the command line."""


app.command(name="get")(get_command)
app.command(name="create")(create_command)
app.command(name="update")(update_command)
app.command(name="delete")(delete_command)
app.add_typer(schema_app, name="schema")
