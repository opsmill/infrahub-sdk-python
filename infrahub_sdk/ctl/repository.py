from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ..async_typer import AsyncTyper
from ..exceptions import FileNotValidError
from ..graphql import Mutation, Query
from ..schema.repository import InfrahubRepositoryConfig
from ..utils import read_file
from .client import initialize_client
from .parameters import CONFIG_PARAM
from .utils import init_logging

app = AsyncTyper()
console = Console()


def get_repository_config(repo_config_file: Path) -> InfrahubRepositoryConfig:
    try:
        config_file_data = load_repository_config_file(repo_config_file)
    except FileNotFoundError as exc:
        console.print(f"[red]File not found {exc}")
        raise typer.Exit(1) from exc
    except FileNotValidError as exc:
        console.print(f"[red]{exc.message}")
        raise typer.Exit(1) from exc

    try:
        data = InfrahubRepositoryConfig(**config_file_data)
    except ValidationError as exc:
        console.print(f"[red]Repository config file not valid, found {len(exc.errors())} error(s)")
        for error in exc.errors():
            loc_str = [str(item) for item in error["loc"]]
            console.print(f"  {'/'.join(loc_str)} | {error['msg']} ({error['type']})")
        raise typer.Exit(1) from exc

    return data


def load_repository_config_file(repo_config_file: Path) -> dict:
    yaml_data = read_file(file_name=repo_config_file)

    try:
        data = yaml.safe_load(yaml_data)
    except yaml.YAMLError as exc:
        raise FileNotValidError(name=str(repo_config_file)) from exc

    return data


@app.callback()
def callback() -> None:
    """
    Manage the repositories in a remote Infrahub instance.

    List, create, delete ..
    """


@app.command()
async def add(
    name: str,
    location: str,
    description: str = "",
    username: Optional[str] = None,
    password: str = "",
    ref: str = "",
    read_only: bool = False,
    debug: bool = False,
    _: str = CONFIG_PARAM,
) -> None:
    """Add a new repository."""

    init_logging(debug=debug)

    input_data = {
        "data": {
            "name": {"value": name},
            "location": {"value": location},
            "description": {"value": description},
        },
    }
    if read_only:
        input_data["data"]["ref"] = {"value": ref}
    else:
        input_data["data"]["default_branch"] = {"value": ref}

    client = initialize_client()

    if username or password:
        credential = await client.create(
            kind="CorePasswordCredential",
            name=name,
            username=username,
            password=password,
        )
        await credential.save(allow_upsert=True)
        input_data["data"]["credential"] = {"id": credential.id}

    query = Mutation(
        mutation="CoreReadOnlyRepositoryCreate" if read_only else "CoreRepositoryCreate",
        input_data=input_data,
        query={"ok": None},
    )

    await client.execute_graphql(query=query.render(), tracker="mutation-repository-create")


@app.command()
async def list(
    branch: Optional[str] = typer.Option(None, help="Branch on which to list repositories."),
    debug: bool = False,
    _: str = CONFIG_PARAM,
) -> None:
    init_logging(debug=debug)

    client = initialize_client()

    repo_status_query = {
        "CoreGenericRepository": {
            "edges": {
                "node": {
                    "__typename": None,
                    "name": {"value": None},
                    "operational_status": {"value": None},
                    "sync_status": {"value": None},
                    "internal_status": {"value": None},
                    "... on CoreReadOnlyRepository": {
                        "ref": {"value": None},
                    },
                }
            }
        },
    }

    query = Query(name="GetRepositoryStatus", query=repo_status_query)
    resp = await client.execute_graphql(query=query.render(), branch_name=branch, tracker="query-repository-list")

    table = Table(title="List of all Repositories")

    table.add_column("Name", justify="right", style="cyan", no_wrap=True)
    table.add_column("Type")
    table.add_column("Operational status")
    table.add_column("Sync status")
    table.add_column("Internal status")
    table.add_column("Ref")

    for repository_node in resp["CoreGenericRepository"]["edges"]:
        repository = repository_node["node"]

        table.add_row(
            repository["name"]["value"],
            repository["__typename"],
            repository["operational_status"]["value"],
            repository["sync_status"]["value"],
            repository["internal_status"]["value"],
            repository["ref"]["value"] if "ref" in repository else "",
        )

    console.print(table)
