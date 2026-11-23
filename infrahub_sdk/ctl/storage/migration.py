from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import random
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TextIO

import httpx

from ...client import _should_refresh_token
from ...exceptions import Error
from ...rate_limit import RateLimitRetryHandler

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

LIST_PATH = "/api/storage/objects"
BATCH_PATH = "/api/storage/objects/encrypt"
OUTCOME_ENCRYPTED = "encrypted"
OUTCOME_FAILED = "failed"
RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_TOO_MANY_REQUESTS = 429
ADMISSION_HEADER = "X-Infrahub-Admission"
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_MAX_SECONDS = 30.0
BACKOFF_JITTER = 0.25
BACKOFF_MAX_EXPONENT = 63
RETRY_AFTER_MAX_SECONDS = 300.0
UNANSWERED_MAX_RETRIES = 3
SMALL_OBJECT_BYTES = 65536
BATCH_MAX_SIZE = 500
PAGE_MAX_SIZE = 5000


class MigrationError(Exception):
    """The run cannot continue: the server refused the request, or stayed unreachable."""


@dataclass
class Totals:
    """Counters of a run; a state file keeps them, so they add up over the runs that resume it."""

    counts: dict[str, int] = field(default_factory=dict)
    bytes_encrypted: int = 0
    bytes_listed: int = 0
    objects_listed: int = 0
    skipped_newer: int = 0
    requests: int = 0
    encrypt_requests: int = 0
    shed_429: int = 0
    shed_429_admission: int = 0
    retries: int = 0
    elapsed_seconds: float = 0.0
    limit_decreases: int = 0
    limit_increases: int = 0
    limit_final: int = 0
    bytes_handled: int = 0
    count_seconds: float = 0.0
    count_requests: int = 0


@dataclass
class Options:
    concurrency: int = 8
    batch_size: int = 50
    page_size: int = 5000
    rate: float | None = None
    priority: str = "low"
    before: datetime | None = None
    dry_run: bool = False
    limit: int | None = None
    allow_unverified: bool = False
    state_file: Path | None = None
    report: Path | None = None
    max_retries: int = 10
    restart: bool = False
    min_concurrency: int = 1
    slow_factor: float = 2.0
    count: bool = False


class Pacer:
    """Space the requests of every worker by the configured rate, and hold them all while the server sheds."""

    def __init__(
        self, rate: float | None, clock: Callable[[], float], sleep: Callable[[float], Awaitable[None]]
    ) -> None:
        self._interval = 1.0 / rate if rate else 0.0
        self._clock = clock
        self._sleep = sleep
        self._next_slot = 0.0
        self._paused_until = 0.0

    async def wait(self) -> None:
        """Return when the caller may send one request."""
        while True:
            now = self._clock()
            if now < self._paused_until:
                await self._sleep(self._paused_until - now)
                continue
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._interval
            if slot > now:
                await self._sleep(slot - now)
            if self._clock() >= self._paused_until:
                return

    def pause(self, seconds: float) -> None:
        """Hold every request for `seconds` from now."""
        self._paused_until = max(self._paused_until, self._clock() + seconds)


class AdaptiveLimit:
    """Number of requests kept in flight, lowered when the server slows down or answers 429.

    The signal is the latency per unit of work of the batches, compared with the lowest smoothed value seen so
    far. A signal above `slow_factor` times that floor, or a 429 answer, halves the limit (at most once per
    cooldown). Otherwise the limit rises by one after every `limit` quiet requests, up to the maximum.
    """

    SMOOTHING = 0.2
    COOLDOWN_SECONDS = 2.0
    FLOOR_DRIFT_PER_SECOND = 0.005

    def __init__(self, maximum: int, minimum: int, slow_factor: float, clock: Callable[[], float]) -> None:
        self.maximum = maximum
        self.minimum = max(1, min(minimum, maximum))
        self.limit = max(self.minimum, maximum // 2)
        self.slow_factor = slow_factor
        self._clock = clock
        self._in_flight = 0
        self._condition = asyncio.Condition()
        self._smoothed: float | None = None
        self._floor = 0.0
        self._floor_at = 0.0
        self._quiet = 0
        self._last_decrease = float("-inf")
        self.decreases = 0
        self.increases = 0

    async def acquire(self) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self._in_flight < self.limit)
            self._in_flight += 1

    async def release(self) -> None:
        async with self._condition:
            self._in_flight -= 1
            self._condition.notify_all()

    def _decrease(self) -> None:
        now = self._clock()
        if now - self._last_decrease < self.COOLDOWN_SECONDS or self.limit <= self.minimum:
            return
        self.limit = max(self.minimum, self.limit // 2)
        self._last_decrease = now
        self._quiet = 0
        self.decreases += 1

    def shed(self) -> None:
        """The server answered 429."""
        self._decrease()

    def observe(self, seconds: float) -> None:
        """Record the latency per unit of work of one batch and adapt the limit."""
        if seconds <= 0:
            return  # A coarse clock can read 0.0; as the first sample it would set the floor to 0 for ever.
        now = self._clock()
        if self._smoothed is None:
            self._smoothed = seconds
            self._floor = seconds
        else:
            self._smoothed += self.SMOOTHING * (seconds - self._smoothed)
            # The floor rises slowly, so one lucky sample does not make every later request look slow for ever.
            drift = 1 + self.FLOOR_DRIFT_PER_SECOND * (now - self._floor_at)
            self._floor = min(self._floor * drift, self._smoothed)
        self._floor_at = now
        if self._smoothed > self.slow_factor * self._floor:
            self._decrease()
            return
        self._quiet += 1
        if self._quiet >= self.limit and self.limit < self.maximum:
            self.limit += 1
            self._quiet = 0
            self.increases += 1


def backoff_delay(attempt: int, rng: random.Random) -> float:
    """Return the delay before retry number `attempt` (1 for the first): exponential, capped, with jitter."""
    delay = min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * 2 ** min(attempt - 1, BACKOFF_MAX_EXPONENT))
    return delay * (1 + BACKOFF_JITTER * rng.random())


_RETRY_AFTER_PARSER = RateLimitRetryHandler(max_retries=0, backoff_base=0.0, backoff_max=RETRY_AFTER_MAX_SECONDS)


def parse_retry_after(value: str | None) -> float:
    """Return the seconds a `Retry-After` header asks for (delta-seconds or HTTP-date); 0 when absent or unusable."""
    if value is None:
        return 0.0
    try:
        seconds = float(value)
    except ValueError:
        return _RETRY_AFTER_PARSER.parse_retry_after(value) or 0.0
    return max(0.0, seconds) if math.isfinite(seconds) else 0.0


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO 8601 timestamp; one without an offset is read as UTC."""
    text = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class StorageEncryptor:
    """Page through the stored objects and have the server encrypt them in batches, at a pace the server accepts.

    The requests go through one `httpx.AsyncClient`, so every request reuses a pooled connection. The client
    answers 429 itself, without the retries of the SDK client, so that every 429 reaches the adaptive limit.
    """

    def __init__(
        self,
        options: Options,
        address: str,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
        on_counted: Callable[[], None] | None = None,
        on_notice: Callable[[str], None] | None = None,
        refresh_login: Callable[[httpx.AsyncClient], Awaitable[None]] | None = None,
    ) -> None:
        self.options = options
        self.on_counted = on_counted
        self.on_notice = on_notice
        self.refresh_login = refresh_login
        self.address = address
        self.totals = Totals()
        self.start_after: str | None = None
        self.completed = False
        self.resumed = False
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._pacer = Pacer(rate=options.rate, clock=clock, sleep=sleep)
        self._started_at = clock()
        self._elapsed_before = 0.0
        self._answered = False
        self._auth_generation = 0
        self._auth_lock = asyncio.Lock()
        self._handled_at_start = 0
        self._bytes_at_start = 0
        self.objects_confirmed = 0
        self.bytes_confirmed = 0
        self.page_interrupted = False
        self.interrupted_counts: dict[str, int] = {}
        self.interrupted_bytes_encrypted = 0
        self.selected_objects = 0
        self.selected_bytes = 0
        self.remaining_objects: int | None = None
        self.remaining_bytes: int | None = None
        self.counting = False
        self.counted_objects = 0
        self.count_seconds_this_run = 0.0
        self._count_requests_before = 0
        self.limit = AdaptiveLimit(
            maximum=options.concurrency,
            minimum=options.min_concurrency,
            slow_factor=options.slow_factor,
            clock=clock,
        )

    def check_output_files(self) -> None:
        """Check that the state file and the report can be written, before any object is changed.

        A dry run writes neither file, so it checks nothing.

        Raises:
            MigrationError: If the directory of a file is missing or not writable, or an existing file is not writable.

        """
        if self.options.dry_run:
            return
        for option, path in (("--state-file", self.options.state_file), ("--report", self.options.report)):
            if path is None:
                continue
            directory = path.parent
            if not directory.is_dir():
                raise MigrationError(
                    f"The directory of {option} {path} does not exist. Create it, or use another path."
                )
            if not os.access(directory, os.W_OK | os.X_OK):
                raise MigrationError(f"The directory of {option} {path} is not writable. Use another path.")
            if path.is_dir() or (path.exists() and not os.access(path, os.W_OK)):
                raise MigrationError(f"The file {path} given to {option} cannot be written. Use another path.")

    def load_state(self) -> None:
        path = self.options.state_file
        if path is None or self.options.restart or not path.exists():
            return
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state["address"] != self.address:
                raise MigrationError(
                    f"The state file {path} belongs to {state['address']}, not to {self.address}. "
                    "Use another --state-file, or --restart to discard it."
                )
            start_after = state["start_after"]
            completed = bool(state["completed"])
            saved = dict(state["totals"])
            known = {item.name for item in fields(Totals)}
            totals = Totals(**{name: value for name, value in saved.items() if name in known})
            if "bytes_handled" not in saved:
                # A state file of an earlier version did not record the bytes of every outcome.
                totals.bytes_handled = totals.bytes_encrypted
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise MigrationError(
                f"The state file {path} cannot be read ({type(exc).__name__}: {exc}). "
                "Delete it or use --restart to start again."
            ) from exc
        if completed:
            return
        self.start_after = start_after
        self.resumed = start_after is not None
        if self.options.dry_run:
            return
        self.totals = totals
        self._elapsed_before = totals.elapsed_seconds
        self._handled_at_start = sum(totals.counts.values())
        self._bytes_at_start = totals.bytes_handled

    def save_state(self) -> None:
        path = self.options.state_file
        if path is None or self.options.dry_run:
            return
        self._update_totals()
        state = {
            "version": 1,
            "address": self.address,
            "start_after": self.start_after,
            "completed": self.completed,
            "totals": asdict(self.totals),
        }
        if self.total_objects is not None:
            state["plan"] = {"objects_total": self.total_objects, "bytes_total": self.total_bytes}
        temporary = path.with_name(f"{path.name}.tmp")
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(state, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)

    @property
    def handled_this_run(self) -> int:
        return sum(self.totals.counts.values()) - self._handled_at_start

    @property
    def seconds_this_run(self) -> float:
        return self._clock() - self._started_at

    @property
    def handled_before(self) -> int:
        """Objects that earlier runs of the same pass handled, from the state file."""
        return self._handled_at_start

    @property
    def done_objects(self) -> int:
        return self._handled_at_start + self.objects_confirmed

    @property
    def done_bytes(self) -> int:
        return self._bytes_at_start + self.bytes_confirmed

    @property
    def total_objects(self) -> int | None:
        """Objects of the whole pass: those earlier runs handled plus those still to do; None without a count."""
        return None if self.remaining_objects is None else self._handled_at_start + self.remaining_objects

    @property
    def total_bytes(self) -> int | None:
        return None if self.remaining_bytes is None else self._bytes_at_start + self.remaining_bytes

    def _update_totals(self) -> None:
        self.totals.elapsed_seconds = self._elapsed_before + (self._clock() - self._started_at)
        self.totals.limit_decreases = self.limit.decreases
        self.totals.limit_increases = self.limit.increases
        self.totals.limit_final = self.limit.limit

    def _check_retries(self, failures: int, path: str, cause: str) -> None:
        allowed = self.options.max_retries if self._answered else min(self.options.max_retries, UNANSWERED_MAX_RETRIES)
        if failures > allowed:
            if self._answered:
                raise MigrationError(f"{path} still fails after {self.options.max_retries} retries: {cause}")
            raise MigrationError(
                f"The server cannot be reached ({cause}), and nothing answered after {allowed} retries."
            )
        self.totals.retries += 1

    async def _request(
        self,
        http: httpx.AsyncClient,
        method: str,
        path: str,
        params: dict[str, Any],
        body: dict[str, Any] | None = None,
    ) -> tuple[httpx.Response, float]:
        """Send one request until the server answers it, waiting out 429 responses and transient failures.

        Returns the answer and the seconds that the HTTP call that produced it took, without the time spent
        waiting for the pace, a pause after a 429 answer or a delay after a failure.

        Raises:
            MigrationError: If the failures other than 429 outnumber the retries allowed.

        """
        failures = 0
        sheds = 0
        refreshed = False
        while True:
            await self._pacer.wait()
            self.totals.requests += 1
            generation = self._auth_generation
            call_started = self._clock()
            try:
                response = await http.request(method, path, params=params, json=body)
            except httpx.TransportError as exc:
                failures += 1
                self._check_retries(failures=failures, path=path, cause=f"{type(exc).__name__}: {exc}")
                await self._sleep(backoff_delay(attempt=failures, rng=self._rng))
                continue
            call_seconds = self._clock() - call_started
            self._answered = True
            if response.status_code == HTTP_TOO_MANY_REQUESTS:
                sheds += 1
                self.totals.shed_429 += 1
                if ADMISSION_HEADER in response.headers:
                    self.totals.shed_429_admission += 1
                self.limit.shed()
                asked = parse_retry_after(response.headers.get("Retry-After"))
                if asked > RETRY_AFTER_MAX_SECONDS:
                    self._notify(
                        f"The server asked for a pause of {asked:.0f} seconds; the command waits "
                        f"{RETRY_AFTER_MAX_SECONDS:.0f} seconds at most, then tries again."
                    )
                    asked = RETRY_AFTER_MAX_SECONDS
                self._pacer.pause(max(asked, backoff_delay(attempt=sheds, rng=self._rng)))
                continue
            if response.status_code in RETRYABLE_STATUS_CODES:
                failures += 1
                self._check_retries(failures=failures, path=path, cause=f"HTTP {response.status_code}")
                await self._sleep(backoff_delay(attempt=failures, rng=self._rng))
                continue
            if (
                response.status_code == HTTP_UNAUTHORIZED
                and self.refresh_login is not None
                and not refreshed
                and _should_refresh_token(response=response)
            ):
                refreshed = True
                await self._renew_login(http, self.refresh_login, seen_generation=generation)
                continue
            return response, call_seconds

    def _notify(self, message: str) -> None:
        if self.on_notice is not None:
            self.on_notice(message)

    async def _renew_login(
        self,
        http: httpx.AsyncClient,
        refresh_login: Callable[[httpx.AsyncClient], Awaitable[None]],
        seen_generation: int,
    ) -> None:
        """Log in again after a 401, once for all the requests that got a 401 with the same token.

        Raises:
            MigrationError: If the new login fails.

        """
        async with self._auth_lock:
            if self._auth_generation != seen_generation:
                return
            try:
                await refresh_login(http)
            except (httpx.HTTPError, Error) as exc:
                raise MigrationError(
                    f"The access token expired and the new login failed ({type(exc).__name__}: {exc})."
                ) from exc
            self._auth_generation += 1

    async def _list_page(self, http: httpx.AsyncClient) -> tuple[list[dict[str, Any]], str | None]:
        return await self._fetch_listing(http, start_after=self.start_after, limit=self.options.page_size)

    async def _fetch_listing(
        self, http: httpx.AsyncClient, start_after: str | None, limit: int
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"limit": limit}
        if start_after:
            params["start_after"] = start_after
        response, _ = await self._request(http, "GET", LIST_PATH, params)
        if response.status_code != HTTP_OK:
            raise MigrationError(refusal_message(response=response, what="The listing of the stored objects"))
        body = answer_body(response, what="The listing of the stored objects")
        try:
            return body["objects"], body["next_start_after"]
        except (KeyError, TypeError) as exc:
            raise MigrationError(f"The listing of the stored objects has an unexpected shape: {exc!r}") from exc

    @staticmethod
    def _check_progress(start_after: str | None, next_start_after: str | None) -> None:
        """Stop when the server points back at the position it was asked to continue after.

        Raises:
            MigrationError: If `next_start_after` equals `start_after`, since the same page would be listed again.

        """
        if next_start_after is not None and next_start_after == start_after:
            raise MigrationError(
                f"The listing of the stored objects does not advance: asked to continue after {start_after!r}, "
                f"the server answered with the same position. The command stops instead of listing the same page "
                "again. The server may be faulty."
            )

    async def _encrypt_batch(self, http: httpx.AsyncClient, stored: list[dict[str, Any]]) -> list[dict[str, Any]]:
        body = {
            "identifiers": [item["identifier"] for item in stored],
            "allow_unverified": self.options.allow_unverified,
        }
        await self.limit.acquire()
        try:
            response, seconds = await self._request(http, "POST", BATCH_PATH, {}, body)
        finally:
            await self.limit.release()
        self.totals.encrypt_requests += 1
        if response.status_code != HTTP_OK:
            raise MigrationError(refusal_message(response=response, what="The request to encrypt a batch"))
        # A batch is compared per unit of work: one unit per object plus one per `SMALL_OBJECT_BYTES` of content.
        batch_bytes = sum(item["size"] for item in stored)
        units = len(stored) + batch_bytes / SMALL_OBJECT_BYTES
        self.limit.observe(seconds / units)
        body = answer_body(response, what="The request to encrypt a batch")
        try:
            results: list[dict[str, Any]] = body["results"]
        except (KeyError, TypeError) as exc:
            raise MigrationError(
                f"The request to encrypt a batch has an answer of an unexpected shape: {exc!r}"
            ) from exc
        self.objects_confirmed += len(results)
        self.bytes_confirmed += batch_bytes
        return results

    def _record(self, result: dict[str, Any], report: TextIO | None) -> None:
        outcome = result["outcome"]
        self.totals.counts[outcome] = self.totals.counts.get(outcome, 0) + 1
        if outcome == OUTCOME_ENCRYPTED:
            self.totals.bytes_encrypted += result["size"]
        elif report is not None:
            report.write(json.dumps(result) + "\n")

    def _keep_interrupted(self, results: list[dict[str, Any]]) -> None:
        """Keep what the server confirmed in a page that did not complete, for the summary only.

        These results are not in `totals`, so the state file never counts them: the rerun repeats the page.
        """
        self.page_interrupted = True
        for result in results:
            outcome = result["outcome"]
            self.interrupted_counts[outcome] = self.interrupted_counts.get(outcome, 0) + 1
            if outcome == OUTCOME_ENCRYPTED:
                self.interrupted_bytes_encrypted += result["size"]

    def _select(self, objects: list[dict[str, Any]], remaining: int | None) -> tuple[list[dict[str, Any]], bool]:
        """Return the objects of a page to work on, and whether the limit of the run cut the page short."""
        selected: list[dict[str, Any]] = []
        for stored in objects:
            if remaining is not None and len(selected) >= remaining:
                return selected, True
            self.start_after = stored["identifier"]
            self.totals.objects_listed += 1
            self.totals.bytes_listed += stored["size"]
            if self.options.before and parse_timestamp(stored["last_modified"]) > self.options.before:
                self.totals.skipped_newer += 1
                continue
            selected.append(stored)
            self.selected_objects += 1
            self.selected_bytes += stored["size"]
        return selected, False

    async def _encrypt_page(
        self, http: httpx.AsyncClient, selected: list[dict[str, Any]], report: TextIO | None
    ) -> None:
        queue: asyncio.Queue[list[dict[str, Any]]] = asyncio.Queue()
        size = self.options.batch_size
        for start in range(0, len(selected), size):
            queue.put_nowait(selected[start : start + size])
        results: list[dict[str, Any]] = []

        async def worker() -> None:
            while True:
                try:
                    batch = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                results.extend(await self._encrypt_batch(http, batch))

        workers = [asyncio.create_task(worker()) for _ in range(min(self.options.concurrency, queue.qsize()))]
        try:
            await asyncio.gather(*workers)
        except BaseException:
            self._keep_interrupted(results)
            raise
        finally:
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        # A page counts only once it is complete, so an interrupted page is redone and never counted twice.
        for result in results:
            self._record(result=result, report=report)
        self.totals.bytes_handled += sum(item["size"] for item in selected)

    async def _count_pass(self, http: httpx.AsyncClient) -> None:
        """List the objects the run will send, from the saved position, and record how many and how large.

        The pass only reads. It applies `--before` and `--limit` as the run does, and uses the largest page size,
        so it neither changes which objects are sent nor needs the page size of the run. The seconds and requests
        it takes are kept apart from the encryption, so the throughput of the run stays comparable.

        Raises:
            MigrationError: If the server refuses the listing or stays unreachable.

        """
        started = self._clock()
        requests_before = self.totals.requests
        self.counting = True
        objects = 0
        total_bytes = 0
        start_after = self.start_after
        limit = self.options.limit
        try:
            while limit is None or objects < limit:
                page, next_start_after = await self._fetch_listing(http, start_after=start_after, limit=PAGE_MAX_SIZE)
                self._check_progress(start_after=start_after, next_start_after=next_start_after)
                for item in page:
                    if self.options.before and parse_timestamp(item["last_modified"]) > self.options.before:
                        continue
                    if limit is not None and objects >= limit:
                        break
                    objects += 1
                    total_bytes += item["size"]
                self.counted_objects = objects
                if next_start_after is None:
                    break
                start_after = next_start_after
        finally:
            self.counting = False
            self.count_seconds_this_run = self._clock() - started
            self.totals.count_requests += self.totals.requests - requests_before
            self.totals.requests = requests_before
        self.remaining_objects = objects
        self.remaining_bytes = total_bytes
        self.totals.count_seconds += self.count_seconds_this_run
        # The time of the count pass is not part of the time of the run, so objects per second stay comparable.
        self._started_at = self._clock()
        if self.on_counted is not None:
            self.on_counted()

    async def run(self, http: httpx.AsyncClient) -> None:
        """Walk the listing from the saved position and encrypt every selected object.

        Raises:
            MigrationError: If the server refuses the run or stays unreachable.

        """
        self.check_output_files()
        self.load_state()
        if self.options.count and not self.options.dry_run:
            await self._count_pass(http)
        processed = 0
        with contextlib.ExitStack() as stack:
            report: TextIO | None = None
            if self.options.report is not None and not self.options.dry_run:
                report = stack.enter_context(self.options.report.open("a", encoding="utf-8"))
            while True:
                remaining = None if self.options.limit is None else self.options.limit - processed
                if remaining is not None and remaining <= 0:
                    break
                position = self.start_after
                objects, next_start_after = await self._list_page(http)
                self._check_progress(start_after=position, next_start_after=next_start_after)
                selected, cut_short = self._select(objects=objects, remaining=remaining)
                if not self.options.dry_run:
                    try:
                        await self._encrypt_page(http, selected, report)
                    except BaseException:
                        self.start_after = position
                        raise
                if not cut_short and next_start_after is not None:
                    # The cursor is the last name the server scanned; it can be past the last listed object.
                    self.start_after = next_start_after
                processed += len(selected)
                if report is not None:
                    report.flush()
                if not cut_short and next_start_after is None:
                    self.completed = True
                self.save_state()
                if cut_short or next_start_after is None:
                    break
        self._update_totals()


def answer_body(response: httpx.Response, what: str) -> Any:
    """Return the JSON body of an answer.

    Raises:
        MigrationError: If the body is not JSON.

    """
    try:
        return response.json()
    except ValueError as exc:
        raise MigrationError(
            f"{what} was answered with HTTP {response.status_code} and a body that is not JSON."
        ) from exc


def refusal_message(response: httpx.Response, what: str) -> str:
    """Return a message that says what a refused request means for the person who runs the command."""
    status = response.status_code
    detail = server_detail(response)
    suffix = f" Server answer: {detail}" if detail else ""
    if status == HTTP_UNAUTHORIZED:
        return f"{what} was refused with HTTP 401: the server does not accept the token or credentials.{suffix}"
    if status == HTTP_FORBIDDEN:
        return (
            f"{what} was refused with HTTP 403: the account of this token does not have the super admin permission "
            f"that encrypting stored objects needs.{suffix}"
        )
    if status == HTTP_NOT_FOUND:
        return (
            f"{what} was refused with HTTP 404: this server does not have the storage encryption routes "
            f"({LIST_PATH}). It runs an Infrahub version without them, or another address is meant.{suffix}"
        )
    if status == HTTP_CONFLICT:
        return (
            f"{what} was refused with HTTP 409: storage encryption is not enabled on the server, or the server "
            f"has no storage key.{suffix}"
        )
    return f"{what} was refused with HTTP {status}.{suffix}"


def printable(text: str) -> str:
    """Replace the characters that a terminal would act on, such as escape sequences, with spaces."""
    return "".join(char if char.isprintable() else " " for char in text)


def server_detail(response: httpx.Response) -> str:
    """Return the message a server error carries, or the start of its body, safe to print."""
    try:
        body = response.json()
    except ValueError:
        return printable(response.text[:300])
    if isinstance(body, dict):
        if isinstance(body.get("detail"), str):
            return printable(str(body["detail"])[:300])
        errors = body.get("errors")
        if isinstance(errors, list):
            messages = [str(item["message"]) for item in errors if isinstance(item, dict) and "message" in item]
            if messages:
                return printable("; ".join(messages)[:300])
    return printable(response.text[:300])
