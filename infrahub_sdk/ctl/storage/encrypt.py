from __future__ import annotations

import asyncio
import contextlib
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.table import Table

from ...constants import Priority
from ..client import initialize_client
from ..parameters import CONFIG_PARAM
from ..utils import catch_exception
from .migration import (
    BATCH_MAX_SIZE,
    OUTCOME_FAILED,
    PAGE_MAX_SIZE,
    MigrationError,
    Options,
    StorageEncryptor,
)
from .progress import (
    ProgressView,
    RateTracker,
    format_bytes,
    format_number,
    format_percent,
    progress_line,
)

console = Console()

DEFAULT_STATE_FILE = Path("infrahub-storage-encrypt.state.json")
DEFAULT_REPORT_FILE = Path("infrahub-storage-encrypt.report.jsonl")
CONCURRENCY_MAX = 64
EXIT_OBJECTS_FAILED = 1
EXIT_STOPPED = 2
EXIT_INTERRUPTED = 130
EXIT_TERMINATED = 143
STOP_SIGNALS = ((signal.SIGINT, "Ctrl-C"), (signal.SIGTERM, "SIGTERM"))
PROGRESS_LINE_SECONDS = 5.0
PROGRESS_LIVE_SECONDS = 0.5


def _check_priority(value: str) -> str:
    try:
        return Priority(value).value
    except ValueError:
        raise typer.BadParameter(f"must be one of {', '.join(item.value for item in Priority)}") from None


def _view(encryptor: StorageEncryptor, rate: float | None) -> ProgressView:
    dry = encryptor.options.dry_run
    totals = encryptor.totals
    return ProgressView(
        done_objects=totals.objects_listed if dry else encryptor.done_objects,
        total_objects=None if dry else encryptor.total_objects,
        done_bytes=totals.bytes_listed if dry else encryptor.done_bytes,
        total_bytes=None if dry else encryptor.total_bytes,
        rate=rate,
        limit=encryptor.limit.limit,
        limit_maximum=encryptor.limit.maximum,
        shed_429=totals.shed_429,
        retries=totals.retries,
    )


def _done_objects(encryptor: StorageEncryptor) -> int:
    return encryptor.totals.objects_listed if encryptor.options.dry_run else encryptor.done_objects


def _done_text(encryptor: StorageEncryptor) -> str:
    """Return `done / total objects (percent)` when the total is known, otherwise the number done."""
    done = _done_objects(encryptor)
    total = None if encryptor.options.dry_run else encryptor.total_objects
    if total is None:
        return f"{format_number(done)} objects"
    return f"{format_number(done)} / {format_number(total)} objects ({format_percent(done=done, total=total)})"


class _Progress:
    """Builds the progress line from counters, with the recent rate for the remaining time."""

    def __init__(self, encryptor: StorageEncryptor) -> None:
        self._encryptor = encryptor
        self._tracker = RateTracker()

    def line(self) -> str:
        encryptor = self._encryptor
        if encryptor.counting:
            self._tracker = RateTracker()
            return f"Counting the objects to process: {format_number(encryptor.counted_objects)} so far"
        self._tracker.record(now=time.monotonic(), done=_done_objects(encryptor))
        return progress_line(_view(encryptor, rate=self._tracker.rate()))


async def _show_progress(encryptor: StorageEncryptor) -> None:
    progress = _Progress(encryptor)
    if console.is_terminal:
        with Live(console=console, transient=True, refresh_per_second=2) as live:
            while True:
                live.update(progress.line())
                await asyncio.sleep(PROGRESS_LIVE_SECONDS)
    # Sample the counters twice per second so the rate has data, and print a line every PROGRESS_LINE_SECONDS.
    next_print = time.monotonic() + PROGRESS_LINE_SECONDS
    while True:
        line = progress.line()
        if time.monotonic() >= next_print:
            console.print(line, highlight=False, soft_wrap=True)
            next_print += PROGRESS_LINE_SECONDS
        await asyncio.sleep(PROGRESS_LIVE_SECONDS)


async def _run_until_stopped(encryptor: StorageEncryptor, http: httpx.AsyncClient) -> str | None:
    """Run the encryption; return the name of the signal that stopped it, after its work in flight was cancelled.

    Ctrl-C (SIGINT) and SIGTERM, which a container or a job runner sends, stop the run in the same way.

    Raises:
        MigrationError: If the run cannot continue.

    """
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    received: list[str] = []

    def request_stop(name: str) -> None:
        received.append(name)
        stop.set()

    installed: list[signal.Signals] = []
    for number, name in STOP_SIGNALS:
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(number, request_stop, name)
            installed.append(number)
    work = asyncio.create_task(encryptor.run(http))
    waiter = asyncio.create_task(stop.wait())
    progress = asyncio.create_task(_show_progress(encryptor))
    try:
        await asyncio.wait({work, waiter}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for number in installed:
            loop.remove_signal_handler(number)
        for task in (waiter, progress):
            task.cancel()
        if not work.done():
            work.cancel()
        await asyncio.gather(waiter, progress, work, return_exceptions=True)
    if work.cancelled():
        return received[0] if received else "Ctrl-C"
    work.result()
    return None


def _announce_count(encryptor: StorageEncryptor) -> None:
    console.print(
        f"To process: {format_number(encryptor.remaining_objects or 0)} objects "
        f"({format_bytes(encryptor.remaining_bytes or 0)})",
        highlight=False,
    )
    if encryptor.handled_before:
        console.print(
            f"Already handled in earlier runs: {format_number(encryptor.handled_before)} objects", highlight=False
        )


def _summary_table(encryptor: StorageEncryptor, options: Options) -> Table:
    totals = encryptor.totals
    seconds = encryptor.seconds_this_run
    handled = encryptor.handled_this_run
    table = Table(show_header=False, title="Storage encryption" + (" (dry run)" if options.dry_run else ""))
    table.add_row("Objects listed", str(totals.objects_listed))
    if options.dry_run:
        table.add_row("Objects that would be sent", str(totals.objects_listed - totals.skipped_newer))
        table.add_row(
            "Bytes that would be sent", f"{encryptor.selected_bytes} ({format_bytes(encryptor.selected_bytes)})"
        )
    elif encryptor.total_objects is not None:
        table.add_row("Objects to process at the start of this run", format_number(encryptor.remaining_objects or 0))
        table.add_row("Handled in earlier runs", format_number(encryptor.handled_before))
        table.add_row("Done in total", _done_text(encryptor))
        table.add_row(
            "Bytes done in total", f"{format_bytes(encryptor.done_bytes)} / {format_bytes(encryptor.total_bytes or 0)}"
        )
        table.add_row("Seconds counting", f"{encryptor.count_seconds_this_run:.1f}")
    for outcome, count in sorted(totals.counts.items()):
        table.add_row(outcome, str(count))
    if options.before:
        table.add_row("Skipped, modified after --before", str(totals.skipped_newer))
    table.add_row("Bytes listed", str(totals.bytes_listed))
    table.add_row("Bytes encrypted", str(totals.bytes_encrypted))
    table.add_row("Requests", f"{totals.requests} ({totals.encrypt_requests} to encrypt a batch)")
    table.add_row("Retries after errors", str(totals.retries))
    table.add_row("Answers 429", f"{totals.shed_429} ({totals.shed_429_admission} with the admission marker)")
    table.add_row(
        "In flight limit",
        f"final {encryptor.limit.limit} of {encryptor.limit.maximum}, "
        f"{encryptor.limit.decreases} decreases, {encryptor.limit.increases} increases",
    )
    table.add_row("Seconds in this run", f"{seconds:.1f}")
    if not options.dry_run and seconds > 0:
        table.add_row("Objects per second", f"{handled / seconds:.1f}")
    table.add_row("Pass finished", "yes" if encryptor.completed else "no")
    return table


@catch_exception(console=console)
async def encrypt_command(
    concurrency: int = typer.Option(
        8,
        min=1,
        max=CONCURRENCY_MAX,
        help="Most batches in flight at once (at most 64); the command starts lower and adapts",
    ),
    batch_size: int = typer.Option(50, min=1, max=BATCH_MAX_SIZE, help="Stored objects in each request to encrypt"),
    page_size: int = typer.Option(
        PAGE_MAX_SIZE, min=1, max=PAGE_MAX_SIZE, help="Stored objects in each listing request"
    ),
    rate: float | None = typer.Option(None, min=0.001, help="Most requests per second (default: no maximum)"),
    priority: str = typer.Option("low", callback=_check_priority, help="Priority of the requests: high, medium or low"),
    before: datetime | None = typer.Option(
        None,
        help="Leave the objects modified after this time (ISO 8601; no offset means UTC)",
        formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"],
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only list: count the objects and their size"),
    limit: int | None = typer.Option(None, min=1, help="Stop after this number of objects"),
    allow_unverified: bool = typer.Option(
        False, "--allow-unverified", help="Also encrypt the objects that no node records a checksum for"
    ),
    state_file: Path = typer.Option(DEFAULT_STATE_FILE, help="Keeps the position in the listing, so a rerun resumes"),
    report: Path = typer.Option(
        DEFAULT_REPORT_FILE, help="Receives one JSON line for each object that was not encrypted"
    ),
    max_retries: int = typer.Option(
        10, min=0, help="Retries of one request after a network error or HTTP 502, 503, 504"
    ),
    timeout: int = typer.Option(300, min=1, help="Seconds before one request times out"),
    restart: bool = typer.Option(False, "--restart", help="Ignore the state file and list from the first object"),
    no_count: bool = typer.Option(
        False,
        "--no-count",
        help="Do not list the objects first to count them; the progress shows no total, percent or remaining time",
    ),
    _: str = CONFIG_PARAM,
) -> None:
    """Encrypt the stored files that were written before storage encryption was enabled.

    The command lists the stored objects page by page and asks the server, which holds the storage key, to encrypt them.

    It keeps several batches in flight, lowers that number when the server slows down, and waits when it answers HTTP 429.

    The token needs the super admin permission, and storage encryption must be enabled on the server.

    The command does its own retries, not those of the SDK client: network errors and HTTP 502, 503 and 504, up to --max-retries.

    Before it encrypts, the command lists the objects still to process, to show the total, the percent done and the remaining time.
    Use --no-count to skip this pass on a very large installation; the progress then shows no total.

    The state file records the position after every page. After an error, Ctrl-C or SIGTERM, run the same command again to resume.

    Objects that the server leaves unchanged are listed in the report file, which every run appends to.
    A run that resumes does not retry them, nor the objects that failed, because the saved position is past them.
    A new full pass, which starts after a pass has finished, or --restart, tries them again.

    \b
    Exit codes:
      0    Every object is encrypted, was already encrypted, or was skipped by the server
      1    The server could not encrypt at least one object, or the command failed before the run
           (for example on a login error, a file error or an unexpected error)
      2    The run stopped on an error from the server or on a state file or report that cannot be used
      130  The run stopped on Ctrl-C (SIGINT)
      143  The run stopped on SIGTERM
    """
    options = Options(
        concurrency=concurrency,
        batch_size=batch_size,
        page_size=page_size,
        rate=rate,
        priority=priority,
        before=before.replace(tzinfo=timezone.utc) if before and before.tzinfo is None else before,
        dry_run=dry_run,
        limit=limit,
        allow_unverified=allow_unverified,
        state_file=state_file,
        report=report,
        max_retries=max_retries,
        restart=restart,
        count=not no_count,
    )
    client = initialize_client(timeout=timeout)
    await client.login()
    encryptor = StorageEncryptor(options=options, address=client.address)
    encryptor.on_counted = lambda: _announce_count(encryptor)
    encryptor.on_notice = lambda message: console.print(escape(message), highlight=False)
    if client.config.password_authentication:

        async def renew_login(http: httpx.AsyncClient) -> None:
            await client.login(refresh=True)
            http.headers["Authorization"] = client.headers["Authorization"]

        encryptor.refresh_login = renew_login
    async with httpx.AsyncClient(
        base_url=client.address,
        headers=client._merge_request_headers({"X-Priority": priority}),
        timeout=client._build_timeout(timeout),
        verify=client.config.tls_context,
        **client._build_proxy_config(),
    ) as http:
        try:
            stopped_by = await _run_until_stopped(encryptor, http)
        except MigrationError as exc:
            console.print(f"[red]Error: {escape(str(exc))}")
            console.print(f"Done before the error: {_done_text(encryptor)}.", highlight=False)
            if not dry_run and state_file.exists():
                console.print(f"Progress is saved in {escape(str(state_file))}; run the same command again to resume.")
            console.print(_summary_table(encryptor, options))
            raise typer.Exit(code=EXIT_STOPPED) from exc

    console.print(_summary_table(encryptor, options))
    if dry_run and stopped_by is None:
        console.print(
            f"To process: {format_number(encryptor.selected_objects)} objects ({format_bytes(encryptor.selected_bytes)})",
            highlight=False,
        )
    if stopped_by is not None:
        console.print(f"Stopped by {stopped_by}. Done: {_done_text(encryptor)}.", highlight=False)
        if not dry_run and state_file.exists():
            console.print(f"Run the same command again to resume from {escape(str(state_file))}.")
        else:
            console.print("Nothing was saved to resume from; run the same command again to start again.")
        raise typer.Exit(code=EXIT_TERMINATED if stopped_by == "SIGTERM" else EXIT_INTERRUPTED)
    if not dry_run and encryptor.totals.counts:
        console.print(f"Objects that were not encrypted are listed in {escape(str(report))}.")
    if encryptor.totals.counts.get(OUTCOME_FAILED, 0):
        raise typer.Exit(code=EXIT_OBJECTS_FAILED)
