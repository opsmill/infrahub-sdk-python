from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any, NoReturn

import httpx

from .exceptions import RateLimitError

if TYPE_CHECKING:
    from .types import InfrahubLoggers

LOGGER = logging.getLogger("infrahub_sdk")


class RateLimitRetryHandler:
    """Retry logic for HTTP 429 responses.

    The decision methods are pure and stateless (the attempt count is passed in per call), so a
    single handler can be shared across concurrent requests. ``send``/``asend`` are the sync and
    async I/O drivers that call the sender once per attempt, sleep between retries, and raise
    ``RateLimitError`` when the budget is exhausted.
    """

    def __init__(
        self,
        max_retries: int,
        backoff_base: float,
        backoff_max: float,
        *,
        enabled: bool = True,
        log: InfrahubLoggers | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.enabled = enabled
        self.log = log or LOGGER

    def parse_retry_after(self, header: str | None, *, now: datetime | None = None) -> float | None:
        """Return the ``Retry-After`` wait in seconds, or ``None`` if absent/unparseable.

        Handles both RFC 7231 forms (delta-seconds and HTTP-date); a past date floors to ``0.0``.
        """
        value = header.strip() if header is not None else ""
        if not value:
            return None

        try:
            return max(0.0, float(int(value)))
        except OverflowError:
            return None
        except ValueError:
            pass  # not an integer; try the HTTP-date form below

        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed is None:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if now is None:
            now = datetime.now(timezone.utc)

        delta = (parsed - now).total_seconds()
        return max(0.0, delta)

    def compute_backoff(self, attempt: int) -> float:
        """Exponential backoff ceiling ``min(backoff_max, backoff_base * 2**attempt)``.

        ``attempt`` is capped at 63 so a very large ``rate_limit_max_retries`` cannot overflow
        ``float`` before the clamp applies.
        """
        return min(self.backoff_max, self.backoff_base * (2 ** min(attempt, 63)))

    def jittered_delay(self, ceiling: float) -> float:
        """Full-jitter delay drawn from ``[0, ceiling]``."""
        return random.uniform(0, ceiling)

    def next_delay(self, attempt: int, retry_after_header: str | None = None, *, now: datetime | None = None) -> float:
        """Return the delay in seconds before the next retry.

        Honours a parseable ``Retry-After`` (clamped to ``backoff_max``); otherwise a jittered
        exponential backoff (already within ``[0, backoff_max]``).
        """
        retry_after = self.parse_retry_after(retry_after_header, now=now)
        if retry_after is not None:
            return min(retry_after, self.backoff_max)
        return self.jittered_delay(self.compute_backoff(attempt))

    def should_retry(self, attempts_made: int) -> bool:
        """Return ``True`` while retries remain (``attempts_made <= max_retries``)."""
        return attempts_made <= self.max_retries

    def _raise_exhausted(self, response: httpx.Response, url: str, attempts: int) -> NoReturn:
        """Raise ``RateLimitError`` once the retry budget is exhausted.

        Chains the underlying ``httpx.HTTPStatusError`` when one is available.

        Raises:
            RateLimitError: Always.

        """
        retry_after = self.parse_retry_after(response.headers.get("Retry-After"))
        cause: httpx.HTTPStatusError | None = None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            cause = exc
        except RuntimeError:
            pass  # response has no attached request (custom/fabricated); nothing to chain
        raise RateLimitError(url=url, attempts=attempts, retry_after=retry_after) from cause

    async def asend(self, send: Callable[[], Coroutine[Any, Any, httpx.Response]], url: str) -> httpx.Response:
        """Send via ``send``, retrying HTTP 429 responses with jittered backoff.

        ``send`` performs one HTTP send per call and MUST yield a fully-readable body each time,
        since it is re-invoked per attempt. Honours ``Retry-After`` when present.

        Raises:
            RateLimitError: If HTTP 429 responses persist past ``max_retries``.

        """
        if not self.enabled:
            return await send()

        attempts = 0
        while True:
            response = await send()
            attempts += 1
            if response.status_code != 429:
                return response

            retry_after_header = response.headers.get("Retry-After")
            if not self.should_retry(attempts_made=attempts):
                self._raise_exhausted(response=response, url=url, attempts=attempts)

            delay = self.next_delay(attempt=attempts - 1, retry_after_header=retry_after_header)
            self.log.warning(f"Rate limited (HTTP 429) on {url}, retry {attempts} in {delay:.2f}s")
            await asyncio.sleep(delay)

    def send(self, send: Callable[[], httpx.Response], url: str) -> httpx.Response:
        """Synchronous counterpart of :meth:`asend`; see it for the full contract."""
        if not self.enabled:
            return send()

        attempts = 0
        while True:
            response = send()
            attempts += 1
            if response.status_code != 429:
                return response

            retry_after_header = response.headers.get("Retry-After")
            if not self.should_retry(attempts_made=attempts):
                self._raise_exhausted(response=response, url=url, attempts=attempts)

            delay = self.next_delay(attempt=attempts - 1, retry_after_header=retry_after_header)
            self.log.warning(f"Rate limited (HTTP 429) on {url}, retry {attempts} in {delay:.2f}s")
            time.sleep(delay)
