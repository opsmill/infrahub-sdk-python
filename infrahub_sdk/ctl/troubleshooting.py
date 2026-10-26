from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..async_typer import AsyncTyper
from .client import initialize_client
from .parameters import CONFIG_PARAM
from .utils import catch_exception

if TYPE_CHECKING:
    import httpx

app = AsyncTyper()
trace_sample_ratio_app = AsyncTyper(help="Read, set or clear the temporary trace sampling ratio.")
app.add_typer(trace_sample_ratio_app, name="trace-sample-ratio")

console = Console()

TRACE_SAMPLE_RATIO_PATH = "/api/troubleshooting/trace-sample-ratio"
MAX_DURATION_SECONDS = 86400

STATE_FIELDS = {
    "enabled": "Tracing enabled",
    "default_ratio": "Default ratio",
    "temporary_ratio": "Temporary ratio",
    "expires_at": "Expires at (UTC)",
    "ratio_in_force": "Ratio in force",
}


def _require_finite_ratio(value: float) -> float:
    # A range check passes `nan`, because every comparison with it is false.
    if not math.isfinite(value):
        raise typer.BadParameter("must be a number from 0 to 1")
    return value


def _print_state(response: httpx.Response) -> None:
    if response.is_error:
        _print_server_errors(response)
        raise typer.Exit(code=1)

    state: dict[str, Any] = response.json()
    table = Table(show_header=False)
    for field, label in STATE_FIELDS.items():
        value = state.get(field)
        table.add_row(label, "" if value is None else escape(str(value)))
    console.print(table)


def _print_server_errors(response: httpx.Response) -> None:
    try:
        errors = response.json().get("errors") or []
    except ValueError:
        errors = []
    messages = [error["message"] for error in errors if isinstance(error, dict) and "message" in error]
    if not messages:
        response.raise_for_status()
    for message in messages:
        console.print(f"[red]{escape(message)}")


@trace_sample_ratio_app.command(name="get")
@catch_exception(console=console)
async def get_trace_sample_ratio(_: str = CONFIG_PARAM) -> None:
    """Show the trace sampling ratio of the API server that answers."""
    client = initialize_client()
    response = await client._get(url=f"{client.address}{TRACE_SAMPLE_RATIO_PATH}")
    _print_state(response)


@trace_sample_ratio_app.command(name="set")
@catch_exception(console=console)
async def set_trace_sample_ratio(
    ratio: float = typer.Option(
        ..., min=0, max=1, callback=_require_finite_ratio, help="Share of new root traces to record"
    ),
    duration: int = typer.Option(..., min=1, max=MAX_DURATION_SECONDS, help="Number of seconds the ratio applies"),
    _: str = CONFIG_PARAM,
) -> None:
    """Set a temporary trace sampling ratio on every API server and task worker."""
    client = initialize_client()
    response = await client._put(
        url=f"{client.address}{TRACE_SAMPLE_RATIO_PATH}",
        payload={"ratio": ratio, "duration_seconds": duration},
    )
    _print_state(response)


@trace_sample_ratio_app.command(name="clear")
@catch_exception(console=console)
async def clear_trace_sample_ratio(_: str = CONFIG_PARAM) -> None:
    """Clear the temporary trace sampling ratio, so every process uses its default ratio again."""
    client = initialize_client()
    response = await client._delete(url=f"{client.address}{TRACE_SAMPLE_RATIO_PATH}")
    _print_state(response)
