import logging

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from ..async_typer import AsyncTyper
from ..utils import calculate_time_diff
from .branch_report import (
    analyze_branch_diffs,
    build_report_items,
    check_git_changes,
    check_proposed_changes,
    display_report,
    get_all_non_default_branches,
)
from .client import initialize_client
from .parameters import CONFIG_PARAM
from .utils import catch_exception

app = AsyncTyper()
console = Console()


DEFAULT_CONFIG_FILE = "infrahubctl.toml"
ENVVAR_CONFIG_FILE = "INFRAHUBCTL_CONFIG"


@app.callback()
def callback() -> None:
    """
    Manage the branches in a remote Infrahub instance.

    List, create, merge, rebase ..
    """


@app.command("list")
@catch_exception(console=console)
async def list_branch(_: str = CONFIG_PARAM) -> None:
    """List all existing branches."""

    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    client = initialize_client()
    branches = await client.branch.all()

    table = Table(title="List of all branches")

    table.add_column("Name", justify="right", style="cyan", no_wrap=True)
    table.add_column("Description")
    table.add_column("Origin Branch")
    table.add_column("Branched From")
    table.add_column("Sync with Git")
    table.add_column("Has Schema Changes")
    table.add_column("Is Default")
    table.add_column("Status")

    # identify the default branch and always print it first
    default_branch = [branch for branch in branches.values() if branch.is_default][0]
    table.add_row(
        default_branch.name,
        default_branch.description or " - ",
        default_branch.origin_branch,
        f"{default_branch.branched_from} ({calculate_time_diff(default_branch.branched_from)})",
        "[green]True" if default_branch.sync_with_git else "[#FF7F50]False",
        "[green]True" if default_branch.has_schema_changes else "[#FF7F50]False",
        "[green]True" if default_branch.is_default else "[#FF7F50]False",
        default_branch.status,
    )

    for branch in branches.values():
        if branch.is_default:
            continue

        table.add_row(
            branch.name,
            branch.description or " - ",
            branch.origin_branch,
            f"{branch.branched_from} ({calculate_time_diff(branch.branched_from)})",
            "[green]True" if branch.sync_with_git else "[#FF7F50]False",
            "[green]True" if default_branch.has_schema_changes else "[#FF7F50]False",
            "[green]True" if branch.is_default else "[#FF7F50]False",
            branch.status,
        )

    console.print(table)


@app.command()
@catch_exception(console=console)
async def create(
    branch_name: str = typer.Argument(..., help="Name of the branch to create"),
    description: str = typer.Option(default="", help="Description of the branch"),
    sync_with_git: bool = typer.Option(
        False, help="Extend the branch to Git and have Infrahub create the branch in connected repositories."
    ),
    isolated: bool = typer.Option(True, hidden=True, help="Set the branch to isolated mode (deprecated)"),  # noqa: ARG001
    _: str = CONFIG_PARAM,
) -> None:
    """Create a new branch."""

    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    client = initialize_client()
    branch = await client.branch.create(branch_name=branch_name, description=description, sync_with_git=sync_with_git)
    console.print(f"Branch {branch_name!r} created successfully ({branch.id}).")


@app.command()
@catch_exception(console=console)
async def delete(branch_name: str, _: str = CONFIG_PARAM) -> None:
    """Delete a branch."""

    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    client = initialize_client()
    await client.branch.delete(branch_name=branch_name)
    console.print(f"Branch '{branch_name}' deleted successfully.")


@app.command()
@catch_exception(console=console)
async def rebase(branch_name: str, _: str = CONFIG_PARAM) -> None:
    """Rebase a Branch with main."""

    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    client = initialize_client()
    await client.branch.rebase(branch_name=branch_name)
    console.print(f"Branch '{branch_name}' rebased successfully.")


@app.command()
@catch_exception(console=console)
async def merge(branch_name: str, _: str = CONFIG_PARAM) -> None:
    """Merge a Branch with main."""

    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    client = initialize_client()
    await client.branch.merge(branch_name=branch_name)
    console.print(f"Branch '{branch_name}' merged successfully.")


@app.command()
@catch_exception(console=console)
async def validate(branch_name: str, _: str = CONFIG_PARAM) -> None:
    """Validate if a branch has some conflict and is passing all the tests (NOT IMPLEMENTED YET)."""

    client = initialize_client()
    await client.branch.validate(branch_name=branch_name)
    console.print(f"Branch '{branch_name}' is valid.")


@app.command("report")
@catch_exception(console=console)
async def report(
    _: str = CONFIG_PARAM,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed error information"),
) -> None:
    """
    Generate a report of branches to help identify candidates for deletion.

    Analyzes branches for:
    - Data changes (via diff)
    - Open proposed changes
    - Git repository changes (for synced branches)

    Errors during analysis are handled gracefully - the command will continue
    analyzing other branches and mark branches with errors conservatively
    (assuming they have changes). Use --verbose to see detailed error information.
    """
    logging.getLogger("infrahub_sdk").setLevel(logging.CRITICAL)

    # Initialize client
    client = initialize_client()

    # Setup Rich progress display
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        # Step 1: Fetch branches
        fetch_task = progress.add_task("Fetching branches...", total=1)
        branches = await get_all_non_default_branches(client)
        progress.update(fetch_task, completed=1)

        if not branches:
            console.print("[yellow]No non-default branches found.")
            return

        # Step 2: Analyze diffs
        diff_results = await analyze_branch_diffs(client, branches, progress)

        # Step 3: Check proposed changes
        pc_results = await check_proposed_changes(client, branches, progress)

        # Step 4: Check Git changes
        git_results = await check_git_changes(client, branches, progress)

        # Step 5: Build report
        build_task = progress.add_task("Building report...", total=1)
        report_items = build_report_items(branches, diff_results, pc_results, git_results)
        progress.update(build_task, completed=1)

    # Display results
    display_report(report_items, branches, console, verbose=verbose)
