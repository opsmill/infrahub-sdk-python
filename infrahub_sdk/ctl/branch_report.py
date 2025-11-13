"""Branch report command implementation for analyzing branches that could be deleted."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from rich.table import Table

from infrahub_sdk.protocols import CoreProposedChange
from infrahub_sdk.timestamp import Timestamp
from infrahub_sdk.utils import calculate_time_diff

if TYPE_CHECKING:
    from rich.console import Console
    from rich.progress import Progress

    from infrahub_sdk.branch import BranchData
    from infrahub_sdk.client import InfrahubClient
    from infrahub_sdk.diff import NodeDiff


# Analysis result models for better encapsulation
class DiffAnalysisResult(BaseModel):
    """Result of diff analysis for a single branch."""

    branch_name: str = Field(description="Name of the branch")
    has_changes: bool = Field(description="Whether the branch has data changes")
    error: str | None = Field(default=None, description="Error message if analysis failed")


class ProposedChangesResult(BaseModel):
    """Result of proposed changes check for a single branch."""

    branch_name: str = Field(description="Name of the branch")
    has_changes: bool = Field(description="Whether the branch has open proposed changes")
    count: int = Field(default=0, description="Number of open proposed changes")
    error: str | None = Field(default=None, description="Error message if check failed")


class GitChangesResult(BaseModel):
    """Result of Git changes check for a single branch."""

    branch_name: str = Field(description="Name of the branch")
    has_changes: bool = Field(description="Whether the branch has Git changes")
    repos_with_changes: list[str] = Field(default_factory=list, description="List of repositories with changes")
    error: str | None = Field(default=None, description="Error message if check failed")


async def get_all_non_default_branches(client: InfrahubClient) -> list[BranchData]:
    """Fetch all branches and filter out the default branch.

    Returns a list of BranchData objects for all non-default branches.
    """
    branches = await client.branch.all()
    return [branch for branch in branches.values() if not branch.is_default]


def _has_diff_changes(node_diffs: list[NodeDiff]) -> bool:
    """Check if any NodeDiff contains actual changes.

    A branch has changes if any node has:
    - action != 'UNCHANGED'
    - OR any element with action != 'UNCHANGED'
    - OR any element with non-zero summary values (added, updated, removed)
    """
    for node_diff in node_diffs:
        # Check if the node itself has changes
        if node_diff.get("action") and node_diff["action"] != "UNCHANGED":
            return True

        # Check if any element has changes
        for element in node_diff.get("elements", []):
            if element.get("action") and element["action"] != "UNCHANGED":
                return True

            # Check summary values
            summary = element.get("summary", {})
            if summary.get("added", 0) > 0 or summary.get("updated", 0) > 0 or summary.get("removed", 0) > 0:
                return True

    return False


async def analyze_branch_diffs(
    client: InfrahubClient, branches: list[BranchData], progress: Progress
) -> list[DiffAnalysisResult]:
    """Analyze each branch for data changes using diff calculation.

    For each branch:
    1. Trigger a diff calculation from branch creation time to now
    2. Query the diff results
    3. Determine if there are any actual changes

    Returns:
        List of DiffAnalysisResult objects, one per branch
    """
    diff_task = progress.add_task("Analyzing branch diffs", total=len(branches))
    results: list[DiffAnalysisResult] = []

    # Get current time for diff calculation
    current_time = Timestamp().to_datetime()

    for branch in branches:
        # Parse the branched_from timestamp
        from_time = Timestamp(branch.branched_from).to_datetime()

        # Generate a unique diff name for this analysis
        diff_name = f"branch-report-{branch.name}-{int(current_time.timestamp())}"

        try:
            # Create and wait for diff calculation to complete
            await client.create_diff(
                branch=branch.name,
                name=diff_name,
                from_time=from_time,
                to_time=current_time,
                wait_until_completion=True,
            )

            # Get the diff summary
            node_diffs = await client.get_diff_summary(
                branch=branch.name,
                name=diff_name,
            )

            # Check if there are any changes
            has_changes = _has_diff_changes(node_diffs)
            results.append(DiffAnalysisResult(branch_name=branch.name, has_changes=has_changes))

        except TimeoutError as exc:
            # Timeout during diff calculation - conservative: assume changes exist
            results.append(
                DiffAnalysisResult(branch_name=branch.name, has_changes=True, error=f"Diff analysis timeout: {exc}")
            )

        except PermissionError as exc:
            # Permission error accessing branch or diff - conservative: assume changes exist
            results.append(
                DiffAnalysisResult(
                    branch_name=branch.name, has_changes=True, error=f"Permission denied during diff analysis: {exc}"
                )
            )

        except Exception as exc:
            # Any other error during diff analysis - conservative: assume changes exist
            results.append(
                DiffAnalysisResult(
                    branch_name=branch.name,
                    has_changes=True,
                    error=f"Diff analysis error: {type(exc).__name__}: {exc}",
                )
            )

        # Update progress
        progress.advance(diff_task)

    return results


async def check_proposed_changes(
    client: InfrahubClient, branches: list[BranchData], progress: Progress
) -> list[ProposedChangesResult]:
    """Check for open proposed changes on each branch.

    Queries all CoreProposedChange objects and counts how many open/closed (but not merged/cancelled)
    proposed changes exist for each branch.

    Returns:
        List of ProposedChangesResult objects, one per branch
    """
    pc_task = progress.add_task("Checking proposed changes", total=1)

    # Initialize results for all branches
    results: list[ProposedChangesResult] = []
    branch_pc_count: dict[str, int] = {}
    global_error: str | None = None

    try:
        # Query all proposed changes - we need source_branch and state
        proposed_changes = await client.filters(
            kind=CoreProposedChange,
            include=["source_branch", "state"],
        )

        # Count open proposed changes per branch
        # States "open" and "closed" are considered active (can be reopened)
        # States "merged" and "cancelled" are final and cannot be reopened
        for pc in proposed_changes:
            branch_name = pc.source_branch.value
            state_value = pc.state.value
            # Only count if state is "open" or "closed" (not merged/cancelled)
            if isinstance(state_value, str) and state_value.lower() in ["open", "closed"]:
                branch_pc_count[branch_name] = branch_pc_count.get(branch_name, 0) + 1

    except PermissionError as exc:
        # Permission error accessing proposed changes
        global_error = f"Permission denied when querying proposed changes: {exc}"

    except Exception as exc:
        # If querying proposed changes fails, we cannot determine PC status
        global_error = f"Error querying proposed changes: {type(exc).__name__}: {exc}"

    # Build results for all branches
    for branch in branches:
        count = branch_pc_count.get(branch.name, 0)
        results.append(
            ProposedChangesResult(branch_name=branch.name, has_changes=count > 0, count=count, error=global_error)
        )

    progress.advance(pc_task)
    return results


async def check_git_changes(
    client: InfrahubClient, branches: list[BranchData], progress: Progress
) -> list[GitChangesResult]:
    """Check for Git changes in repositories for branches synced with Git.

    For each branch with sync_with_git=True:
    1. Query all repositories to get commit information per branch
    2. Compare the commit on each branch with the commit on the default branch
    3. If commits differ, the branch has Git changes in that repository

    Returns:
        List of GitChangesResult objects, one per branch
    """
    git_task = progress.add_task("Checking Git repositories", total=len(branches))

    # Initialize results for all branches
    results: list[GitChangesResult] = []
    branch_git_data: dict[str, tuple[bool, list[str]]] = {}
    global_error: str | None = None

    try:
        # Get repository information across all branches
        # This will query CoreGenericRepository which includes both CoreRepository and CoreReadOnlyRepository
        branches_dict = {branch.name: branch for branch in branches}
        repositories = await client.get_list_repositories(branches=branches_dict)

        # For each branch, check if it has different commits than the default branch
        for branch in branches:
            # Only check branches that are synced with Git
            if not branch.sync_with_git:
                branch_git_data[branch.name] = (False, [])
                progress.advance(git_task)
                continue

            repos_with_changes: list[str] = []

            # Check each repository for differences
            for repo_name, repo_data in repositories.items():
                # Get commit for this branch
                branch_commit = repo_data.branches.get(branch.name)
                if not branch_commit:
                    # Branch doesn't exist in this repository (or hasn't been synced yet)
                    continue

                # Get commit for the default branch
                default_commit = repo_data.branches.get(client.default_branch)
                if not default_commit:
                    # Default branch doesn't have this repository (unlikely but handle gracefully)
                    continue

                # If commits differ, there are Git changes
                if branch_commit != default_commit:
                    repos_with_changes.append(repo_name)

            # Store results
            has_changes = len(repos_with_changes) > 0
            branch_git_data[branch.name] = (has_changes, repos_with_changes)

            progress.advance(git_task)

    except PermissionError as exc:
        # Permission error accessing repositories
        global_error = f"Permission denied when querying Git repositories: {exc}"
        # Mark synced branches as having potential changes (conservative)
        for branch in branches:
            if branch.sync_with_git:
                branch_git_data[branch.name] = (True, [])
            progress.advance(git_task)

    except Exception as exc:
        # If querying repositories fails, we cannot determine Git status
        global_error = f"Error querying Git repositories: {type(exc).__name__}: {exc}"
        # Mark synced branches as having potential changes (conservative)
        for branch in branches:
            if branch.sync_with_git:
                branch_git_data[branch.name] = (True, [])
            progress.advance(git_task)

    # Build results for all branches
    for branch in branches:
        has_changes, repos = branch_git_data.get(branch.name, (False, []))
        # Only set error for branches that are synced with Git
        error = global_error if global_error and branch.sync_with_git else None
        results.append(
            GitChangesResult(branch_name=branch.name, has_changes=has_changes, repos_with_changes=repos, error=error)
        )

    return results


def build_report_items(
    branches: list[BranchData],
    diff_results: list[DiffAnalysisResult],
    pc_results: list[ProposedChangesResult],
    git_results: list[GitChangesResult],
) -> list[BranchReportItem]:
    """Aggregate all analysis results into BranchReportItem objects.

    Combines data from:
    - Branch data (name, description, sync_with_git, status)
    - Diff analysis results (has_data_changes)
    - Proposed changes results (has_proposed_changes, count)
    - Git analysis results (has_git_changes, repositories)
    - Error information from all analysis steps

    Calculates can_be_deleted based on:
    - No data changes AND
    - No open proposed changes AND
    - No Git changes (or not synced with Git)

    Returns:
        List of BranchReportItem objects, sorted by can_be_deleted (deletable first), then by name
    """
    # Create lookup dictionaries for easier access
    diff_map = {result.branch_name: result for result in diff_results}
    pc_map = {result.branch_name: result for result in pc_results}
    git_map = {result.branch_name: result for result in git_results}

    report_items: list[BranchReportItem] = []

    for branch in branches:
        # Get results for this branch
        diff_result = diff_map.get(branch.name)
        pc_result = pc_map.get(branch.name)
        git_result = git_map.get(branch.name)

        # Extract data with conservative defaults if not found
        has_data_changes = diff_result.has_changes if diff_result else True
        has_pcs = pc_result.has_changes if pc_result else False
        pc_count = pc_result.count if pc_result else 0
        has_git_changes_bool = git_result.has_changes if git_result else False
        git_repos = git_result.repos_with_changes if git_result else []

        # Collect errors for this branch
        branch_errors: list[str] = []
        if diff_result and diff_result.error:
            branch_errors.append(diff_result.error)
        if pc_result and pc_result.error:
            branch_errors.append(pc_result.error)
        if git_result and git_result.error:
            branch_errors.append(git_result.error)

        # For Git changes, if branch is not synced with Git, set to None
        has_git_changes: bool | None = has_git_changes_bool if branch.sync_with_git else None

        # Calculate if branch can be deleted:
        # - No data changes
        # - No open proposed changes
        # - No Git changes (or not synced with Git, in which case has_git_changes is None)
        can_be_deleted = not has_data_changes and not has_pcs and (has_git_changes is None or not has_git_changes)

        # Create the report item
        report_item = BranchReportItem(
            branch_name=branch.name,
            description=branch.description,
            sync_with_git=branch.sync_with_git,
            has_data_changes=has_data_changes,
            has_proposed_changes=has_pcs,
            proposed_changes_count=pc_count,
            has_git_changes=has_git_changes,
            git_repositories_checked=git_repos,
            can_be_deleted=can_be_deleted,
            status=branch.status,
            errors=branch_errors,
        )

        report_items.append(report_item)

    # Sort by can_be_deleted (deletable first), then by branch name
    report_items.sort(key=lambda item: (not item.can_be_deleted, item.branch_name))

    return report_items


class BranchReportItem(BaseModel):
    """Contains all analysis results for a single branch."""

    branch_name: str = Field(description="Name of the branch")
    description: str | None = Field(default=None, description="Branch description")
    sync_with_git: bool = Field(description="Whether branch is synced with Git repositories")
    has_data_changes: bool = Field(description="Whether branch has any data changes (from diff analysis)")
    has_proposed_changes: bool = Field(description="Whether branch has open proposed changes")
    proposed_changes_count: int = Field(default=0, description="Number of open proposed changes")
    has_git_changes: bool | None = Field(
        default=None, description="Whether branch has uncommitted Git changes (None if not synced with Git)"
    )
    git_repositories_checked: list[str] = Field(default_factory=list, description="List of Git repos checked")
    can_be_deleted: bool = Field(description="True if no changes in any category (data, proposed changes, or Git)")
    status: str = Field(description="Branch status (e.g., OPEN, CLOSED)")
    errors: list[str] = Field(
        default_factory=list, description="List of errors encountered during analysis of this branch"
    )


class BranchReportSummary(BaseModel):
    """Overall summary statistics for the branch report."""

    total_branches: int = Field(description="Total number of branches analyzed")
    deletable_branches: int = Field(description="Number of branches that can potentially be deleted")
    branches_with_data_changes: int = Field(description="Number of branches with data changes")
    branches_with_proposed_changes: int = Field(description="Number of branches with open proposed changes")
    branches_with_git_changes: int = Field(description="Number of branches with uncommitted Git changes")
    branches_synced_with_git: int = Field(description="Number of branches synced with Git")


def calculate_summary(report_items: list[BranchReportItem]) -> BranchReportSummary:
    """Calculate summary statistics from the report items.

    Args:
        report_items: List of BranchReportItem objects

    Returns:
        BranchReportSummary with aggregated statistics
    """
    total = len(report_items)
    deletable = sum(1 for item in report_items if item.can_be_deleted)
    with_data_changes = sum(1 for item in report_items if item.has_data_changes)
    with_proposed_changes = sum(1 for item in report_items if item.has_proposed_changes)
    with_git_changes = sum(1 for item in report_items if item.has_git_changes)
    synced_with_git = sum(1 for item in report_items if item.sync_with_git)

    return BranchReportSummary(
        total_branches=total,
        deletable_branches=deletable,
        branches_with_data_changes=with_data_changes,
        branches_with_proposed_changes=with_proposed_changes,
        branches_with_git_changes=with_git_changes,
        branches_synced_with_git=synced_with_git,
    )


def display_report(
    report_items: list[BranchReportItem], branches: list[BranchData], console: Console, verbose: bool = False
) -> None:
    """Display the branch report in a formatted Rich table with summary.

    Args:
        report_items: List of BranchReportItem objects to display
        branches: List of original BranchData objects (for branched_from timestamp)
        console: Rich Console instance for output
        verbose: If True, display detailed error information for branches with errors
    """
    if not report_items:
        console.print("[yellow]No branches to report on.")
        return

    # Create a mapping of branch names to BranchData for quick lookup
    branch_data_map = {branch.name: branch for branch in branches}

    # Create the table
    table = Table(title="Branch Report", show_header=True, header_style="bold magenta")
    table.add_column("Branch Name", style="cyan", no_wrap=True)
    table.add_column("Age", style="dim")
    table.add_column("Data Changes", justify="center")
    table.add_column("Proposed Changes", justify="center")
    table.add_column("Git Changes", justify="center")
    table.add_column("Can Delete?", justify="center")
    table.add_column("Status", style="dim")

    # Add rows for each branch
    for item in report_items:
        # Get age from branched_from timestamp
        branch_data = branch_data_map.get(item.branch_name)
        age = calculate_time_diff(branch_data.branched_from) if branch_data else "Unknown"

        # Format data changes with color (show warning if error occurred)
        if item.errors and any("Diff analysis" in err for err in item.errors):
            data_changes = "[yellow]⚠[/yellow]"
        elif item.has_data_changes:
            data_changes = "[red]✗[/red]"
        else:
            data_changes = "[green]✓[/green]"

        # Format proposed changes with count and color (show warning if error occurred)
        if item.errors and any("proposed changes" in err.lower() for err in item.errors):
            proposed_changes = "[yellow]⚠[/yellow]"
        elif item.has_proposed_changes:
            proposed_changes = f"[red]{item.proposed_changes_count}[/red]"
        else:
            proposed_changes = "[green]0[/green]"

        # Format Git changes with color (N/A if not synced, show warning if error occurred)
        if item.has_git_changes is None:
            git_changes = "[dim]N/A[/dim]"
        elif item.errors and any("Git" in err for err in item.errors):
            git_changes = "[yellow]⚠[/yellow]"
        elif item.has_git_changes:
            # Show which repos have changes if available
            if item.git_repositories_checked:
                repos_str = ", ".join(item.git_repositories_checked)
                git_changes = f"[red]✗[/red] ({repos_str})"
            else:
                git_changes = "[red]✗[/red]"
        else:
            git_changes = "[green]✓[/green]"

        # Format can_be_deleted with color and emphasis
        can_delete = "[bold green]✓[/bold green]" if item.can_be_deleted else "[red]✗[/red]"

        # Add row to table
        table.add_row(
            item.branch_name,
            age or "Unknown",
            data_changes,
            proposed_changes,
            git_changes,
            can_delete,
            item.status,
        )

    # Display the table
    console.print()
    console.print(table)
    console.print()

    # Calculate and display summary
    summary = calculate_summary(report_items)

    console.print("[bold]Summary:[/bold]")
    console.print(f"  Total branches analyzed: {summary.total_branches}")
    console.print(f"  [green]Branches that can potentially be deleted: {summary.deletable_branches}[/green]")
    console.print(f"  [red]Branches with data changes: {summary.branches_with_data_changes}[/red]")
    console.print(f"  [red]Branches with proposed changes: {summary.branches_with_proposed_changes}[/red]")
    console.print(
        f"  [red]Branches with Git changes: {summary.branches_with_git_changes}[/red] "
        f"(out of {summary.branches_synced_with_git} synced with Git)"
    )

    # Count and display errors if any occurred
    branches_with_errors = sum(1 for item in report_items if item.errors)
    if branches_with_errors > 0:
        console.print(f"  [yellow]Branches with errors during analysis: {branches_with_errors}[/yellow]")

    console.print()

    # Display detailed error information in verbose mode
    if verbose and branches_with_errors > 0:
        console.print("[bold yellow]Detailed Error Information:[/bold yellow]")
        console.print()
        for item in report_items:
            if item.errors:
                console.print(f"[cyan]{item.branch_name}[/cyan]:")
                for error in item.errors:
                    console.print(f"  [yellow]•[/yellow] {error}")
                console.print()
        console.print(
            "[dim]Note: Errors are handled conservatively - branches with errors are assumed to have changes.[/dim]"
        )
        console.print()
