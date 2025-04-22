from __future__ import annotations

import logging
import sys
from asyncio import run as aiorun
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from ..ctl import config
from ..ctl.client import initialize_client
from ..ctl.exceptions import QueryNotFoundError
from ..ctl.repository import get_repository_config
from ..ctl.utils import catch_exception, execute_graphql_query
from ..exceptions import ModuleImportError

if TYPE_CHECKING:
    from .. import InfrahubClient
    from ..checks import InfrahubCheck
    from ..schema.repository import InfrahubCheckDefinitionConfig, InfrahubRepositoryConfig

app = typer.Typer()
console = Console()


@dataclass
class CheckModule:
    name: str
    check_class: type[InfrahubCheck]
    definition: InfrahubCheckDefinitionConfig


@app.callback()
def callback() -> None:
    """
    Execute user-defined checks.
    """


@app.command()
@catch_exception(console=console)
def run(
    *,
    path: str,
    debug: bool,
    format_json: bool,
    list_available: bool,
    variables: dict[str, str],
    name: Optional[str] = None,
    branch: Optional[str] = None,
) -> None:
    """Locate and execute all checks under the defined path."""

    log_level = "DEBUG" if debug else "INFO"
    FORMAT = "%(message)s"
    logging.basicConfig(level=log_level, format=FORMAT, datefmt="[%X]", handlers=[RichHandler()])

    repository_config = get_repository_config(Path(config.INFRAHUB_REPO_CONFIG_FILE))

    if list_available:
        list_checks(repository_config=repository_config)
        return

    check_definitions = repository_config.check_definitions
    if name:
        check_definitions = [repository_config.get_check_definition(name=name)]

    check_modules = get_modules(check_definitions=check_definitions)
    aiorun(
        run_checks(
            check_modules=check_modules,
            format_json=format_json,
            path=path,
            variables=variables,
            branch=branch,
            repository_config=repository_config,
        )
    )


async def run_check(
    check_module: CheckModule,
    client: InfrahubClient,
    format_json: bool,
    path: str,
    repository_config: InfrahubRepositoryConfig,
    branch: str | None = None,
    params: dict | None = None,
) -> bool:
    module_name = check_module.name
    output = "stdout" if format_json else None
    log = logging.getLogger("infrahub")
    passed = True
    check_class = check_module.check_class
    check = check_class(client=client, params=params, output=output, root_directory=path, branch=branch)
    param_log = f" - {params}" if params else ""
    try:
        data = execute_graphql_query(
            query=check.query,
            variables_dict=check.params,
            repository_config=repository_config,
            branch=branch,
            debug=False,
        )
        passed = await check.run(data)
        if passed:
            if not format_json:
                log.info(f"{module_name}::{check}: [green]PASSED[/]{param_log}", extra={"markup": True})
        else:
            passed = False
            if not format_json:
                log.error(f"{module_name}::{check}: [red]FAILED[/]{param_log}", extra={"markup": True})

                for log_message in check.logs:
                    log.error(f"  {log_message['message']}")

    except QueryNotFoundError as exc:
        log.warning(f"{module_name}::{check}: unable to find query ({exc!s})")
        passed = False
    except Exception as exc:
        log.warning(f"{module_name}::{check}: An error occurred during execution ({exc})")
        passed = False

    return passed


async def run_targeted_check(
    check_module: CheckModule,
    client: InfrahubClient,
    format_json: bool,
    path: str,
    repository_config: InfrahubRepositoryConfig,
    variables: dict[str, str],
    branch: str | None = None,
) -> bool:
    filters = {}
    param_value = list(check_module.definition.parameters.values())
    if param_value:
        filters[param_value[0]] = check_module.definition.targets

    param_key = list(check_module.definition.parameters.keys())
    identifier = None
    if param_key:
        identifier = param_key[0]

    check_summary: list[bool] = []
    if variables:
        result = await run_check(
            check_module=check_module,
            client=client,
            format_json=format_json,
            path=path,
            branch=branch,
            params=variables,
            repository_config=repository_config,
        )
        check_summary.append(result)
    else:
        targets = await client.get(kind="CoreGroup", include=["members"], **filters)
        await targets.members.fetch()
        for member in targets.members.peers:
            check_parameter = {}
            if identifier:
                attribute = getattr(member.peer, identifier)
                check_parameter = {identifier: attribute.value}
            result = await run_check(
                check_module=check_module,
                client=client,
                format_json=format_json,
                path=path,
                branch=branch,
                params=check_parameter,
                repository_config=repository_config,
            )
            check_summary.append(result)

    return all(check_summary)


async def run_checks(
    check_modules: list[CheckModule],
    format_json: bool,
    path: str,
    variables: dict[str, str],
    repository_config: InfrahubRepositoryConfig,
    branch: str | None = None,
) -> None:
    log = logging.getLogger("infrahub")

    check_summary: list[bool] = []
    client = initialize_client(branch=branch)
    for check_module in check_modules:
        if check_module.definition.targets:
            result = await run_targeted_check(
                check_module=check_module,
                client=client,
                repository_config=repository_config,
                format_json=format_json,
                path=path,
                variables=variables,
                branch=branch,
            )
            check_summary.append(result)
        else:
            result = await run_check(
                check_module=check_module,
                client=client,
                format_json=format_json,
                path=path,
                branch=branch,
                repository_config=repository_config,
            )
            check_summary.append(result)

    if not check_modules:
        if not format_json:
            log.warning("No check found")
        else:
            print('{"level": "WARNING", "message": "message", ""No check found"}')

    if not all(check_summary):
        sys.exit(1)


def get_modules(check_definitions: list[InfrahubCheckDefinitionConfig]) -> list[CheckModule]:
    modules = []
    for check_definition in check_definitions:
        module_name = check_definition.file_path.stem

        relative_path = str(check_definition.file_path.parent) if check_definition.file_path.parent != Path() else None

        try:
            check_class = check_definition.load_class(import_root=str(Path.cwd()), relative_path=relative_path)
        except ModuleImportError as exc:
            console.print(f"[red]{exc.message}")
            raise typer.Exit(1) from exc

        modules.append(CheckModule(name=module_name, check_class=check_class, definition=check_definition))

    return modules


def list_checks(repository_config: InfrahubRepositoryConfig) -> None:
    console.print(f"Python checks defined in repository: {len(repository_config.check_definitions)}")

    for check in repository_config.check_definitions:
        target = check.targets or "-global-"
        console.print(f"{check.name} ({check.file_path}::{check.class_name}) Target: {target}")
