from __future__ import annotations

import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


class RateLimitRetryHandler:
    """Pure, I/O-free decision logic for retrying HTTP 429 responses.

    The handler performs no sleeping and no network I/O; it only computes delays and
    decides whether another retry should be attempted. This keeps it deterministic and
    unit-testable in isolation. The current attempt count is passed in per call so a
    single handler instance can be shared safely across concurrent requests.
    """

    def __init__(self, max_retries: int, backoff_base: float, backoff_max: float) -> None:
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

    def parse_retry_after(self, header: str | None, *, now: datetime | None = None) -> float | None:
        """Return the number of seconds to wait per a ``Retry-After`` header value.

        Supports both RFC 7231 forms:
        - delta-seconds: ``int(header)`` seconds.
        - HTTP-date: ``(parsedate_to_datetime(header) - now).total_seconds()``, floored at 0
          (a past date yields ``0.0``, never a negative value).

        Anything absent, empty, or unparseable returns ``None`` so the caller falls back to
        computed backoff.
        """
        value = header.strip() if header is not None else ""
        if not value:
            return None

        # delta-seconds form
        try:
            return max(0.0, float(int(value)))
        except OverflowError:
            # A pathological, arbitrarily long digit string overflows float(); fall back to
            # computed backoff rather than crashing.
            return None
        except ValueError:
            # Not a delta-seconds integer (e.g. an HTTP-date); fall through to date parsing.
            pass

        # HTTP-date form
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
        """Deterministic exponential ceiling: ``min(backoff_max, backoff_base * 2**attempt)``."""
        return min(self.backoff_max, self.backoff_base * (2**attempt))

    def jittered_delay(self, ceiling: float) -> float:
        """Full jitter: ``random.uniform(0, ceiling)``."""
        return random.uniform(0, ceiling)

    def next_delay(self, attempt: int, retry_after_header: str | None = None, *, now: datetime | None = None) -> float:
        """Return the delay (seconds) before the next retry.

        Honours a parseable ``Retry-After`` header (clamped to ``backoff_max``); otherwise
        returns a jittered exponential backoff, also clamped to ``backoff_max``.
        """
        retry_after = self.parse_retry_after(retry_after_header, now=now)
        if retry_after is not None:
            return min(retry_after, self.backoff_max)
        return min(self.jittered_delay(self.compute_backoff(attempt)), self.backoff_max)

    def should_retry(self, attempts_made: int) -> bool:
        """Return ``True`` while retries remain (``attempts_made <= max_retries``)."""
        return attempts_made <= self.max_retries
