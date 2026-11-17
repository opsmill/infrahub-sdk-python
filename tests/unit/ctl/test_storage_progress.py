from __future__ import annotations

from dataclasses import dataclass

import pytest

from infrahub_sdk.ctl.storage.progress import (
    ProgressView,
    RateTracker,
    format_bytes,
    format_duration,
    format_number,
    format_percent,
    progress_line,
    remaining_text,
)


def view(**overrides: float | None) -> ProgressView:
    values: dict[str, int | float | None] = {
        "done_objects": 1000,
        "total_objects": 4000,
        "done_bytes": 2_000_000_000,
        "total_bytes": 8_000_000_000,
        "rate": 100.0,
        "limit": 6,
        "limit_maximum": 8,
        "shed_429": 2,
        "retries": 1,
    }
    values.update(overrides)
    return ProgressView(**values)  # type: ignore[arg-type]


@dataclass
class FormatCase:
    name: str
    value: float
    expected: str


BYTE_CASES = [
    FormatCase(name="zero", value=0, expected="0 B"),
    FormatCase(name="below-a-kilobyte", value=999, expected="999 B"),
    FormatCase(name="one-kilobyte", value=1000, expected="1.0 kB"),
    FormatCase(name="gigabytes", value=23_400_000_000, expected="23.4 GB"),
    FormatCase(name="petabytes", value=3 * 10**15, expected="3.0 PB"),
    FormatCase(name="beyond-the-largest-unit", value=2 * 10**18, expected="2000.0 PB"),
    FormatCase(name="negative-is-zero", value=-5, expected="0 B"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in BYTE_CASES])
def test_format_bytes(case: FormatCase) -> None:
    assert format_bytes(int(case.value)) == case.expected


DURATION_CASES = [
    FormatCase(name="seconds", value=45, expected="45s"),
    FormatCase(name="zero", value=0, expected="0s"),
    FormatCase(name="minutes", value=185, expected="3m 05s"),
    FormatCase(name="hours", value=7620, expected="2h 07m"),
    FormatCase(name="days", value=3 * 86400 + 4 * 3600, expected="3d 04h"),
    FormatCase(name="more-than-99-days", value=100 * 86400, expected=">99d"),
    FormatCase(name="infinite", value=float("inf"), expected="unknown"),
    FormatCase(name="not-a-number", value=float("nan"), expected="unknown"),
    FormatCase(name="negative", value=-1, expected="unknown"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in DURATION_CASES])
def test_format_duration(case: FormatCase) -> None:
    assert format_duration(case.value) == case.expected


def test_format_number_groups_thousands_for_very_large_numbers() -> None:
    assert format_number(157_000) == "157,000"
    assert format_number(12_345_678_901) == "12,345,678,901"


@dataclass
class PercentCase:
    name: str
    done: int
    total: int
    expected: str


PERCENT_CASES = [
    PercentCase(name="start", done=0, total=100, expected="0.0%"),
    PercentCase(name="half", done=50, total=100, expected="50.0%"),
    PercentCase(name="rounds-down-so-100-means-finished", done=9999, total=10000, expected="99.9%"),
    PercentCase(name="finished", done=100, total=100, expected="100.0%"),
    PercentCase(name="more-objects-than-counted", done=130, total=100, expected="100.0%"),
    PercentCase(name="nothing-to-process", done=0, total=0, expected="100.0%"),
    PercentCase(name="huge", done=10**12, total=4 * 10**12, expected="25.0%"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in PERCENT_CASES])
def test_format_percent(case: PercentCase) -> None:
    assert format_percent(done=case.done, total=case.total) == case.expected


def test_the_rate_is_unknown_until_the_samples_span_enough_time() -> None:
    tracker = RateTracker(window=30, minimum_span=4)
    assert tracker.rate() is None
    tracker.record(now=0, done=0)
    assert tracker.rate() is None
    tracker.record(now=3, done=300)
    assert tracker.rate() is None
    tracker.record(now=5, done=500)
    assert tracker.rate() == pytest.approx(100.0)


def test_the_rate_follows_the_last_window_and_not_the_average_since_the_start() -> None:
    tracker = RateTracker(window=30, minimum_span=4)
    # 100 objects/s for 60 s, then 10 objects/s for 40 s.
    for second in range(0, 101, 2):
        done = second * 100 if second <= 60 else 6000 + (second - 60) * 10
        tracker.record(now=second, done=done)
    average_since_start = 6400 / 100
    assert tracker.rate() == pytest.approx(10.0)
    assert tracker.rate() != pytest.approx(average_since_start)


def test_the_rate_is_zero_when_nothing_progressed_in_the_window() -> None:
    tracker = RateTracker(window=30, minimum_span=4)
    tracker.record(now=0, done=500)
    tracker.record(now=10, done=500)
    assert tracker.rate() == pytest.approx(0.0)


def test_the_rate_is_never_negative() -> None:
    tracker = RateTracker(window=30, minimum_span=4)
    tracker.record(now=0, done=500)
    tracker.record(now=10, done=400)
    assert tracker.rate() == pytest.approx(0.0)


def test_the_progress_line_shows_done_total_percent_rate_remaining_bytes_limit_429_and_retries() -> None:
    line = progress_line(view())

    assert line == (
        "1,000 / 4,000 objects (25.0%) | 100 objects/s | remaining 30s | 2.0 GB / 8.0 GB | limit 6/8 | 429: 2 | retries: 1"
    )


def test_the_progress_line_says_estimating_until_there_is_a_rate() -> None:
    line = progress_line(view(rate=None))

    assert "| estimating |" in line
    assert "remaining estimating" in line


def test_the_progress_line_with_a_rate_of_zero_does_not_divide_by_zero() -> None:
    line = progress_line(view(rate=0.0))

    assert "0 objects/s" in line
    assert "remaining unknown" in line


def test_the_progress_line_with_nothing_to_process() -> None:
    line = progress_line(view(done_objects=0, total_objects=0, done_bytes=0, total_bytes=0, rate=None))

    assert line.startswith("0 / 0 objects (100.0%)")
    assert "remaining finishing" in line
    assert "0 B / 0 B" in line


def test_the_progress_line_when_more_objects_appeared_than_were_counted() -> None:
    line = progress_line(view(done_objects=4200, total_objects=4000))

    assert line.startswith("4,200 / 4,000 objects (100.0%)")
    assert "remaining finishing" in line


def test_the_progress_line_without_a_total_shows_no_total_percent_or_remaining_time() -> None:
    line = progress_line(view(total_objects=None, total_bytes=None))

    assert line == "1,000 objects | 100 objects/s | 2.0 GB | limit 6/8 | 429: 2 | retries: 1"
    assert "%" not in line
    assert "remaining" not in line
    assert "/ 4" not in line


def test_the_progress_line_with_very_large_numbers() -> None:
    line = progress_line(
        view(
            done_objects=1_234_567_890,
            total_objects=9_876_543_210,
            done_bytes=5 * 10**15,
            total_bytes=4 * 10**16,
            rate=2_500_000.0,
        )
    )

    assert line.startswith("1,234,567,890 / 9,876,543,210 objects (12.4%) | 2,500,000 objects/s | remaining ")
    assert "5.0 PB / 40.0 PB" in line


def test_the_remaining_time_is_the_objects_left_divided_by_the_recent_rate() -> None:
    assert remaining_text(view(done_objects=0, total_objects=36_000, rate=10.0)) == "1h 00m"
    assert remaining_text(view(done_objects=0, total_objects=36_000, rate=20.0)) == "30m 00s"
