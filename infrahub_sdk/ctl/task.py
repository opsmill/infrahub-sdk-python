from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..async_typer import AsyncTyper
from ..task.manager import TaskFilter
from ..task.models import Task, TaskState
from .client import initialize_client
from .parameters import CONFIG_PARAM
from .utils import catch_exception, init_logging

app = AsyncTyper()
console = Console()


@app.callback()
def callback() -> None:
    """Manage Infrahub tasks."""


def _parse_states(states: list[str] | None) -> list[TaskState] | None:
    if not states:
        return None

    parsed_states: list[TaskState] = []
    for state in states:
        normalized_state = state.strip().upper()
        try:
            parsed_states.append(TaskState(normalized_state))
        except ValueError as exc:  # pragma: no cover - typer will surface this as CLI error
            raise typer.BadParameter(
                f"Unsupported state '{state}'. Available states: {', '.join(item.value.lower() for item in TaskState)}"
            ) from exc

    return parsed_states


def _render_table(tasks: list[Task]) -> None:
    table = Table(title="Infrahub Tasks", box=None)
    table.add_column("ID", style="cyan", overflow="fold")
    table.add_column("Title", style="magenta", overflow="fold")
    table.add_column("State", style="green")
    table.add_column("Progress", justify="right")
    table.add_column("Workflow", overflow="fold")
    table.add_column("Branch", overflow="fold")
    table.add_column("Updated")

    if not tasks:
        table.add_row("-", "No tasks found", "-", "-", "-", "-", "-")
        console.print(table)
        return

    for task in tasks:
        progress = f"{task.progress:.0%}" if task.progress is not None else "-"
        table.add_row(
            task.id,
            task.title,
            task.state.value,
            progress,
            task.workflow or "-",
            task.branch or "-",
            task.updated_at.isoformat(),
        )

    console.print(table)


@app.command(name="list")
@catch_exception(console=console)
async def list_tasks(
    state: list[str] = typer.Option(
        None, "--state", "-s", help="Filter by task state. Can be provided multiple times."
    ),
    limit: Optional[int] = typer.Option(None, help="Maximum number of tasks to retrieve."),
    offset: Optional[int] = typer.Option(None, help="Offset for pagination."),
    include_related_nodes: bool = typer.Option(False, help="Include related nodes in the output."),
    include_logs: bool = typer.Option(False, help="Include task logs in the output."),
    json_output: bool = typer.Option(False, "--json", help="Output the result as JSON."),
    debug: bool = False,
    _: str = CONFIG_PARAM,
) -> None:
    """List Infrahub tasks."""

    init_logging(debug=debug)

    client = initialize_client()
    filters = TaskFilter()
    parsed_states = _parse_states(state)
    if parsed_states:
        filters.state = parsed_states

    tasks = await client.task.filter(
        filter=filters,
        limit=limit,
        offset=offset,
        include_related_nodes=include_related_nodes,
        include_logs=include_logs,
    )

    if json_output:
        console.print_json(
            data=[task.model_dump(mode="json") for task in tasks], indent=2, sort_keys=True, highlight=False
        )
        return

    _render_table(tasks)
