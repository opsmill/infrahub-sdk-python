from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console

from ..ctl import config
from ..ctl.client import initialize_client
from ..ctl.repository import get_repository_config
from ..ctl.utils import execute_graphql_query, init_logging, parse_cli_vars
from ..exceptions import ModuleImportError
from ..node import InfrahubNode

if TYPE_CHECKING:
    from ..schema.repository import InfrahubRepositoryConfig


async def run(
    generator_name: str,
    path: str,  # noqa: ARG001
    debug: bool,
    list_available: bool,
    branch: str | None = None,
    variables: Optional[list[str]] = None,
) -> None:
    init_logging(debug=debug)
    repository_config = get_repository_config(Path(config.INFRAHUB_REPO_CONFIG_FILE))

    if list_available or not generator_name:
        list_generators(repository_config=repository_config)
        return

    generator_config = repository_config.get_generator_definition(name=generator_name)

    console = Console()
    relative_path = str(generator_config.file_path.parent) if generator_config.file_path.parent != Path() else None

    try:
        generator_class = generator_config.load_class(import_root=str(Path.cwd()), relative_path=relative_path)
    except ModuleImportError as exc:
        console.print(f"[red]{exc.message}")
        raise typer.Exit(1) from exc

    variables_dict = parse_cli_vars(variables)

    param_key = list(generator_config.parameters.keys())
    identifier = None
    if param_key:
        identifier = param_key[0]

    client = initialize_client(branch=branch)
    if variables_dict:
        data = execute_graphql_query(
            query=generator_config.query,
            variables_dict=variables_dict,
            branch=branch,
            debug=False,
            repository_config=repository_config,
        )
        generator = generator_class(
            query=generator_config.query,
            client=client,
            branch=branch or "",
            params=variables_dict,
            convert_query_response=generator_config.convert_query_response,
            infrahub_node=InfrahubNode,
        )
        await generator._init_client.schema.all(branch=generator.branch_name)
        await generator.run(identifier=generator_config.name, data=data)

    else:
        targets = await client.get(
            kind="CoreGroup", branch=branch, include=["members"], name__value=generator_config.targets
        )
        await targets.members.fetch()

        if not targets.members.peers:
            console.print(
                f"[red]No members found within '{generator_config.targets}', not running generator '{generator_name}'"
            )
            return

        for member in targets.members.peers:
            check_parameter = {}
            if identifier:
                attribute = getattr(member.peer, identifier)
                check_parameter = {identifier: attribute.value}
            params = {"name": member.peer.name.value}
            generator = generator_class(
                query=generator_config.query,
                client=client,
                branch=branch or "",
                params=params,
                convert_query_response=generator_config.convert_query_response,
                infrahub_node=InfrahubNode,
            )
            data = execute_graphql_query(
                query=generator_config.query,
                variables_dict=check_parameter,
                branch=branch,
                debug=False,
                repository_config=repository_config,
            )
            await generator._init_client.schema.all(branch=generator.branch_name)
            await generator.run(identifier=generator_config.name, data=data)


def list_generators(repository_config: InfrahubRepositoryConfig) -> None:
    console = Console()
    console.print(f"Generators defined in repository: {len(repository_config.generator_definitions)}")

    for generator in repository_config.generator_definitions:
        console.print(f"{generator.name} ({generator.file_path}::{generator.class_name}) Target: {generator.targets}")
