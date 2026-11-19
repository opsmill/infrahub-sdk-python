from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

RATE_WINDOW_SECONDS = 30.0
RATE_MINIMUM_SPAN_SECONDS = 4.0
RATE_MAXIMUM_GAP_SECONDS = 5.0
MINIMUM_SAMPLES = 2
BYTES_PER_UNIT = 1000
BYTE_UNITS = ("B", "kB", "MB", "GB", "TB", "PB")
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400
LONGEST_DURATION_DAYS = 99


class RateTracker:
    """Rate of progress over the last `window` seconds, so the remaining time follows the current speed.

    The caller records `(time, done)` once per progress refresh, which costs two numbers per refresh. The rate
    stays unknown until the recorded samples span `minimum_span` seconds.

    The refresh runs twice per second, so two samples more than `maximum_gap` seconds apart mean the process did
    not run in between (for example after SIGSTOP). The samples before the gap are dropped, because a rate over a
    span that holds the pause says nothing about the current speed.
    A stall of the server does not make a gap: the refresh goes on and the rate falls.
    """

    def __init__(
        self,
        window: float = RATE_WINDOW_SECONDS,
        minimum_span: float = RATE_MINIMUM_SPAN_SECONDS,
        maximum_gap: float = RATE_MAXIMUM_GAP_SECONDS,
    ) -> None:
        self._window = window
        self._minimum_span = minimum_span
        self._maximum_gap = maximum_gap
        self._samples: deque[tuple[float, int]] = deque()

    def record(self, now: float, done: int) -> None:
        if self._samples and now - self._samples[-1][0] > self._maximum_gap:
            self._samples.clear()
        self._samples.append((now, done))
        # Keep one sample at or before the start of the window, so the window is always fully covered.
        while len(self._samples) > MINIMUM_SAMPLES and self._samples[1][0] <= now - self._window:
            self._samples.popleft()

    def rate(self) -> float | None:
        """Return objects per second over the window, or None while there is too little data."""
        if len(self._samples) < MINIMUM_SAMPLES:
            return None
        first_time, first_done = self._samples[0]
        last_time, last_done = self._samples[-1]
        span = last_time - first_time
        if span < self._minimum_span:
            return None
        return max(0.0, (last_done - first_done) / span)


@dataclass
class ProgressView:
    """What the progress line shows; `total_objects` is None when the count pass was skipped."""

    done_objects: int
    total_objects: int | None
    done_bytes: int
    total_bytes: int | None
    rate: float | None
    limit: int
    limit_maximum: int
    shed_429: int
    retries: int


def format_number(value: int) -> str:
    return f"{value:,}"


def format_bytes(value: int) -> str:
    """Return `value` bytes in decimal units with one decimal, for example `23.4 GB`."""
    size = float(max(0, value))
    unit = 0
    while size >= BYTES_PER_UNIT and unit < len(BYTE_UNITS) - 1:
        size /= BYTES_PER_UNIT
        unit += 1
    return f"{int(size)} B" if unit == 0 else f"{size:.1f} {BYTE_UNITS[unit]}"


def format_duration(seconds: float) -> str:
    """Return a time span as `45s`, `3m 05s`, `2h 07m` or `3d 04h`; more than 99 days is `>99d`."""
    if math.isnan(seconds) or math.isinf(seconds) or seconds < 0:
        return "unknown"
    whole = round(seconds)
    days, rest = divmod(whole, SECONDS_PER_DAY)
    if days > LONGEST_DURATION_DAYS:
        return f">{LONGEST_DURATION_DAYS}d"
    hours, rest = divmod(rest, SECONDS_PER_HOUR)
    minutes, secs = divmod(rest, SECONDS_PER_MINUTE)
    if days:
        return f"{days}d {hours:02d}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_percent(done: int, total: int) -> str:
    """Return the share done, rounded down to one decimal and never above 100%, so 100.0% means finished."""
    if total <= 0:
        return "100.0%"
    return f"{min(100.0, math.floor(done * 1000 / total) / 10):.1f}%"


def remaining_seconds(view: ProgressView) -> float | None:
    """Return the seconds left at the recent rate, or None when the rate or the total is unknown or zero."""
    if view.total_objects is None or view.rate is None or view.rate <= 0:
        return None
    return max(0, view.total_objects - view.done_objects) / view.rate


def remaining_text(view: ProgressView) -> str:
    if view.total_objects is not None and view.done_objects >= view.total_objects:
        return "finishing"
    if view.rate is None:
        return "estimating"
    seconds = remaining_seconds(view)
    return "unknown" if seconds is None else format_duration(seconds)


def progress_line(view: ProgressView) -> str:
    """Return the progress line: done / total, percent, rate, remaining time, bytes, limit, 429 answers, retries."""
    rate = "estimating" if view.rate is None else f"{view.rate:,.0f} objects/s"
    parts: list[str] = []
    if view.total_objects is None:
        parts.extend([f"{format_number(view.done_objects)} objects", rate, format_bytes(view.done_bytes)])
    else:
        percent = format_percent(done=view.done_objects, total=view.total_objects)
        parts.extend(
            [
                f"{format_number(view.done_objects)} / {format_number(view.total_objects)} objects ({percent})",
                rate,
                f"remaining {remaining_text(view)}",
                f"{format_bytes(view.done_bytes)} / {format_bytes(view.total_bytes or 0)}",
            ]
        )
    parts.extend([f"limit {view.limit}/{view.limit_maximum}", f"429: {view.shed_429}", f"retries: {view.retries}"])
    return " | ".join(parts)
