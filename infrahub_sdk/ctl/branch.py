import logging
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.table import Table

from ..async_typer import AsyncTyper
from ..branch import BranchData
from ..diff import DiffTreeData
from ..protocols import CoreProposedChange
from ..utils import calculate_time_diff, decode_json
from .client import initialize_client
from .parameters import CONFIG_PARAM
from .utils import catch_exception

if TYPE_CHECKING:
    from ..client import InfrahubClient

app = AsyncTyper()
console = Console()


DEFAULT_CONFIG_FILE = "infrahubctl.toml"
ENVVAR_CONFIG_FILE = "INFRAHUBCTL_CONFIG"


def format_timestamp(timestamp: str) -> str:
    """Format ISO timestamp to 'YYYY-MM-DD HH:MM:SS'.
    Args:
        timestamp (str): ISO fromatted timestamp

    Returns:
        (str): the datetime as string formatted as 'YYYY-MM-DD HH:MM:SS'

    Raises:
        Any execptions returned from formatting the timestamp are propogated to the caller
    """
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def check_git_files_changed(client: "InfrahubClient", branch: str) -> bool:
    """Check if there are any Git file changes in a branch.

    Args:
        client: Infrahub client instance
        branch: Branch name to check

    Returns:
        True if files have changed, False otherwise

    Raises:
        Any exceptions from the API call are propagated to the caller
    """
    url = f"{client.address}/api/diff/files?branch={branch}"
    resp = await client._get(url=url, timeout=client.default_timeout)
    resp.raise_for_status()
    data = decode_json(response=resp)

    # Check if any repository has files
    if branch in data:
        for repo_data in data[branch].values():
            if isinstance(repo_data, dict) and "files" in repo_data and len(repo_data["files"]) > 0:
                return True

    return False


def generate_branch_report_table(
    branch: BranchData, diff_tree: DiffTreeData | None, git_files_changed: bool | None
) -> Table:
    branch_table = Table(show_header=False, box=None)
    branch_table.add_column(justify="left")
    branch_table.add_column(justify="right")

    branch_table.add_row("Created at", format_timestamp(branch.branched_from))

    status_value = branch.status.value if hasattr(branch.status, "value") else str(branch.status)
    branch_table.add_row("Status", status_value)

    branch_table.add_row("Synced with Git", "Yes" if branch.sync_with_git else "No")

    if git_files_changed is not None:
        branch_table.add_row("Git files changed", "Yes" if git_files_changed else "No")
    else:
        branch_table.add_row("Git files changed", "N/A")

    branch_table.add_row("Has schema changes", "Yes" if branch.has_schema_changes else "No")

    if diff_tree:
        branch_table.add_row("Diff last updated", format_timestamp(diff_tree["to_time"]))
        branch_table.add_row("Amount of additions", str(diff_tree["num_added"]))
        branch_table.add_row("Amount of deletions", str(diff_tree["num_removed"]))
        branch_table.add_row("Amount of updates", str(diff_tree["num_updated"]))
        branch_table.add_row("Amount of conflicts", str(diff_tree["num_conflicts"]))
    else:
        branch_table.add_row("Diff last updated", "No diff available")
        branch_table.add_row("Amount of additions", "-")
        branch_table.add_row("Amount of deletions", "-")
        branch_table.add_row("Amount of updates", "-")
        branch_table.add_row("Amount of conflicts", "-")

    return branch_table


def generate_proposed_change_tables(proposed_changes: list[CoreProposedChange]) -> list[Table]:
    proposed_change_tables: list[Table] = []

    for pc in proposed_changes:
        # Create proposal table
        proposed_change_table = Table(show_header=False, box=None)
        proposed_change_table.add_column(justify="left")
        proposed_change_table.add_column(justify="right")

        # Extract data from node
        proposed_change_table.add_row("Name", pc.name.value)
        proposed_change_table.add_row("State", str(pc.state.value))
        proposed_change_table.add_row("Is draft", "Yes" if pc.is_draft.value else "No")
        proposed_change_table.add_row("Created by", pc.created_by.peer.name.value)  # type: ignore[union-attr]
        proposed_change_table.add_row("Created at", format_timestamp(str(pc.created_by.updated_at)))
        proposed_change_table.add_row("Approvals", str(len(pc.approved_by.peers)))
        proposed_change_table.add_row("Rejections", str(len(pc.rejected_by.peers)))

        proposed_change_tables.append(proposed_change_table)

    return proposed_change_tables


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
    default_branch = next(branch for branch in branches.values() if branch.is_default)
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


@app.command()
@catch_exception(console=console)
async def report(
    branch_name: str = typer.Argument(..., help="Branch name to generate report for"),
    update_diff: bool = typer.Option(False, "--update-diff", help="Update diff before generating report"),
    _: str = CONFIG_PARAM,
) -> None:
    """Generate branch cleanup status report."""

    client = initialize_client()

    # Fetch branch metadata first (needed for diff creation)
    branch = await client.branch.get(branch_name=branch_name)

    if branch.is_default:
        console.print("[red]Cannot create a report for the default branch!")
        sys.exit(1)

    # Update diff if requested
    if update_diff:
        console.print("Updating diff...")
        # Create diff from branch creation to now
        from_time = datetime.fromisoformat(branch.branched_from.replace("Z", "+00:00"))
        to_time = datetime.now(timezone.utc)
        await client.create_diff(
            branch=branch_name,
            name=f"report-{branch_name}",
            from_time=from_time,
            to_time=to_time,
        )
        console.print("Diff updated\n")

    diff_tree = await client.get_diff_tree(branch=branch_name)

    git_files_changed = await check_git_files_changed(client, branch=branch_name)

    proposed_changes = await client.filters(
        kind=CoreProposedChange,  # type: ignore[type-abstract]
        source_branch__value=branch_name,
        include=["created_by"],
        prefetch_relationships=True,
        property=True,
    )

    branch_table = generate_branch_report_table(branch=branch, diff_tree=diff_tree, git_files_changed=git_files_changed)
    proposed_change_tables = generate_proposed_change_tables(proposed_changes=proposed_changes)

    console.print()
    console.print(f"[bold]Branch: {branch_name}[/bold]")

    console.print(branch_table)
    console.print()

    if not proposed_changes:
        console.print("No proposed changes for this branch")
        console.print()

    for proposed_change, proposed_change_table in zip(proposed_changes, proposed_change_tables, strict=True):
        console.print(f"Proposed change: {proposed_change.name.value}")
        console.print(proposed_change_table)
        console.print()
