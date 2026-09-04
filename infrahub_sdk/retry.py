from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable, Coroutine, Iterable
from typing import TYPE_CHECKING, Any

from .exceptions import ServerNotReachableError, ServerNotResponsiveError

if TYPE_CHECKING:
    import httpx

    from .types import InfrahubLoggers

LOGGER = logging.getLogger("infrahub_sdk")

DEFAULT_RETRY_STATUS_CODES: frozenset[int] = frozenset({500, 502, 503, 504})
"""HTTP status codes treated as transient unless ``retry_status_codes`` says otherwise."""

ESCALATE_AFTER_SECONDS = 300.0
"""Once an operation has been retrying for this long, retry log lines switch from WARNING to ERROR."""

TRANSIENT_EXCEPTIONS = (ServerNotReachableError, ServerNotResponsiveError)
"""Client-side failures (connection error, read timeout) that are always considered transient."""


class RetryState:
    """Retry bookkeeping for one logical operation.

    ``execute_graphql`` creates a state and hands it down to ``_request`` so the transport-level
    retries (network errors, timeouts, transient HTTP statuses) and the GraphQL-envelope retries
    (transient ``errors`` inside a 200 response) share a single time budget and attempt counter.
    """

    __slots__ = ("attempts", "started")

    def __init__(self, started: float) -> None:
        self.started = started
        self.attempts = 0


class TransientRetryHandler:
    """Retry policy for transient failures, enabled by ``retry_on_failure``.

    A failure is transient when it is a connection error, a read timeout, an HTTP response whose
    status is listed in ``status_codes``, or a GraphQL error envelope in which every error carries
    one of those statuses in its ``extensions`` (Infrahub sets ``extensions.http_status`` on the
    GraphQL endpoint and an integer ``extensions.code`` on the REST endpoints). Anything else is
    raised immediately, so a bad query or a schema error still fails fast even when the budget is
    unlimited.

    Retries are spaced with exponential backoff (``base_delay * 2**(attempt - 1)``, capped at
    ``max_delay``) with equal jitter, and stop once ``max_duration`` seconds have elapsed since the
    operation started. ``max_duration == 0`` means retry indefinitely.

    The decision methods are pure so a single handler can be shared across concurrent requests;
    ``send``/``asend`` are the sync and async drivers.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        base_delay: float,
        max_delay: float,
        max_duration: float,
        status_codes: Iterable[int] = DEFAULT_RETRY_STATUS_CODES,
        log: InfrahubLoggers | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = enabled
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_duration = max_duration
        self.status_codes = frozenset(status_codes)
        self.log = log or LOGGER
        self.clock = clock

    @property
    def unlimited(self) -> bool:
        """``True`` when there is no time limit on retries (``max_duration == 0``)."""
        return self.max_duration == 0

    def new_state(self) -> RetryState:
        """Start the retry bookkeeping for a new logical operation."""
        return RetryState(started=self.clock())

    # --- Classification -------------------------------------------------------------------------

    def is_transient_status(self, status_code: int) -> bool:
        """Return ``True`` when ``status_code`` is one of the retryable HTTP statuses."""
        return status_code in self.status_codes

    @staticmethod
    def graphql_error_status(error: Any) -> int | None:
        """Return the HTTP status Infrahub attached to a formatted GraphQL error, if any.

        Looks at ``extensions.http_status`` first (GraphQL endpoint) and falls back to an integer
        ``extensions.code`` (REST endpoints). Booleans are rejected since ``bool`` subclasses ``int``.
        """
        if not isinstance(error, dict):
            return None
        extensions = error.get("extensions")
        if not isinstance(extensions, dict):
            return None
        for key in ("http_status", "code"):
            value = extensions.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    def is_transient_graphql_errors(self, errors: Any) -> bool:
        """Return ``True`` when ``errors`` is a non-empty list whose every entry carries a transient status.

        A single error without a status, or with a non-transient one, makes the whole response
        non-transient: it is safer to surface an unclassified failure than to retry it forever.
        """
        if not isinstance(errors, list) or not errors:
            return False
        for error in errors:
            status = self.graphql_error_status(error)
            if status is None or not self.is_transient_status(status):
                return False
        return True

    @staticmethod
    def describe_graphql_errors(errors: list[dict[str, Any]]) -> str:
        """One-line description of a transient GraphQL error envelope for the retry log."""
        first = errors[0]
        status = TransientRetryHandler.graphql_error_status(first)
        message = first.get("message", "")
        suffix = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
        return f"GraphQL error with HTTP status {status}: {message}{suffix}"

    # --- Budget ---------------------------------------------------------------------------------

    def elapsed(self, state: RetryState) -> float:
        """Seconds since the operation tracked by ``state`` started."""
        return self.clock() - state.started

    def remaining(self, state: RetryState) -> float | None:
        """Seconds left in the budget, or ``None`` when retries are unlimited."""
        if self.unlimited:
            return None
        return max(0.0, self.max_duration - self.elapsed(state))

    def should_retry(self, state: RetryState) -> bool:
        """Return ``True`` while retrying is enabled and the time budget is not exhausted."""
        if not self.enabled:
            return False
        if self.unlimited:
            return True
        return self.elapsed(state) < self.max_duration

    # --- Delay ----------------------------------------------------------------------------------

    def compute_backoff(self, attempt: int) -> float:
        """Backoff ceiling for retry number ``attempt`` (1-based): ``min(max_delay, base_delay * 2**(attempt - 1))``.

        The exponent is capped so a very long-running unlimited retry cannot overflow ``float``.
        """
        exponent = min(max(attempt - 1, 0), 63)
        return min(self.max_delay, self.base_delay * (2**exponent))

    def jittered_delay(self, ceiling: float) -> float:
        """Equal-jitter delay drawn from ``[ceiling / 2, ceiling]``."""
        return random.uniform(ceiling / 2, ceiling)

    def next_delay(self, state: RetryState) -> float:
        """Delay before retry number ``state.attempts``, never sleeping past the remaining budget."""
        delay = self.jittered_delay(self.compute_backoff(state.attempts))
        remaining = self.remaining(state)
        if remaining is not None:
            delay = min(delay, remaining)
        return delay

    # --- Drivers --------------------------------------------------------------------------------

    def prepare_retry(self, state: RetryState, url: str, reason: str) -> float:
        """Record one more attempt, log it, and return how long to sleep before it.

        Log lines are emitted at WARNING and escalate to ERROR once the operation has been
        retrying for ``ESCALATE_AFTER_SECONDS``, so an indefinitely retrying job stays visible.
        """
        state.attempts += 1
        delay = self.next_delay(state)
        elapsed = self.elapsed(state)
        budget = "no time limit" if self.unlimited else f"{self.max_duration:.0f}s budget"
        message = (
            f"Transient failure on {url}: {reason}. "
            f"Retry {state.attempts} in {delay:.1f}s ({elapsed:.0f}s elapsed, {budget})"
        )
        if elapsed >= ESCALATE_AFTER_SECONDS:
            self.log.error(message)
        else:
            self.log.warning(message)
        return delay

    async def asleep_before_retry(self, state: RetryState, url: str, reason: str) -> None:
        """Async: record the attempt, log it, and wait for the computed delay."""
        await asyncio.sleep(self.prepare_retry(state=state, url=url, reason=reason))

    def sleep_before_retry(self, state: RetryState, url: str, reason: str) -> None:
        """Sync: record the attempt, log it, and wait for the computed delay."""
        time.sleep(self.prepare_retry(state=state, url=url, reason=reason))

    async def asend(
        self,
        send: Callable[[], Coroutine[Any, Any, httpx.Response]],
        url: str,
        state: RetryState | None = None,
    ) -> httpx.Response:
        """Send via ``send``, retrying transient failures until success or budget exhaustion.

        ``send`` performs one HTTP send per call and is re-invoked per attempt. Pass ``state`` to
        share the budget with an outer retry loop. When the budget runs out the last transient
        exception is re-raised, or the last transient response is returned for the caller to
        handle as it would without retries.

        Raises:
            ServerNotReachableError: If connection errors persist past the budget.
            ServerNotResponsiveError: If read timeouts persist past the budget.

        """
        if not self.enabled:
            return await send()

        state = state or self.new_state()
        while True:
            try:
                response = await send()
            except TRANSIENT_EXCEPTIONS as exc:
                if not self.should_retry(state):
                    raise
                await self.asleep_before_retry(state=state, url=url, reason=str(exc))
                continue

            if not self.is_transient_status(response.status_code) or not self.should_retry(state):
                return response
            await self.asleep_before_retry(state=state, url=url, reason=f"HTTP {response.status_code}")

    def send(
        self,
        send: Callable[[], httpx.Response],
        url: str,
        state: RetryState | None = None,
    ) -> httpx.Response:
        """Synchronous counterpart of :meth:`asend`; see it for the full contract."""
        if not self.enabled:
            return send()

        state = state or self.new_state()
        while True:
            try:
                response = send()
            except TRANSIENT_EXCEPTIONS as exc:
                if not self.should_retry(state):
                    raise
                self.sleep_before_retry(state=state, url=url, reason=str(exc))
                continue

            if not self.is_transient_status(response.status_code) or not self.should_retry(state):
                return response
            self.sleep_before_retry(state=state, url=url, reason=f"HTTP {response.status_code}")
