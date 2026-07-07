"""Unit tests for the pure ``RateLimitRetryHandler`` decision logic.

These tests exercise the handler in isolation (no I/O, no sleeping): exponential-backoff
growth and clamping, full-jitter bounds, ``Retry-After`` parsing (delta-seconds, HTTP-date,
past dates, malformed input), ``next_delay`` selection/clamping, and the retry budget.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from infrahub_sdk.rate_limit import RateLimitRetryHandler


def make_handler(max_retries: int = 5, backoff_base: float = 0.5, backoff_max: float = 60.0) -> RateLimitRetryHandler:
    return RateLimitRetryHandler(max_retries=max_retries, backoff_base=backoff_base, backoff_max=backoff_max)


def test_compute_backoff_grows_exponentially() -> None:
    handler = make_handler(backoff_base=0.5, backoff_max=60.0)
    assert handler.compute_backoff(0) == pytest.approx(0.5)
    assert handler.compute_backoff(1) == pytest.approx(1.0)
    assert handler.compute_backoff(2) == pytest.approx(2.0)
    assert handler.compute_backoff(3) == pytest.approx(4.0)
    # Monotonic non-decreasing.
    values = [handler.compute_backoff(attempt) for attempt in range(8)]
    assert values == sorted(values)


def test_compute_backoff_clamped_to_backoff_max() -> None:
    handler = make_handler(backoff_base=0.5, backoff_max=10.0)
    # 0.5 * 2**10 = 512 -> clamped to 10.0
    assert handler.compute_backoff(10) == pytest.approx(10.0)
    assert handler.compute_backoff(20) == pytest.approx(10.0)


def test_jittered_delay_within_bounds() -> None:
    handler = make_handler()
    for _ in range(100):
        delay = handler.jittered_delay(4.0)
        assert 0.0 <= delay <= 4.0


def test_jittered_delay_varies() -> None:
    handler = make_handler()
    draws = {handler.jittered_delay(10.0) for _ in range(50)}
    # A sample of full-jitter draws should not all be identical.
    assert len(draws) > 1


def test_parse_retry_after_delta_seconds() -> None:
    handler = make_handler()
    assert handler.parse_retry_after("30") == pytest.approx(30.0)
    assert handler.parse_retry_after("0") == pytest.approx(0.0)


def test_parse_retry_after_http_date() -> None:
    handler = make_handler()
    now = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
    future = now + timedelta(seconds=120)
    header = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert handler.parse_retry_after(header, now=now) == pytest.approx(120.0, abs=1.0)


def test_parse_retry_after_past_date_is_zero() -> None:
    handler = make_handler()
    now = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
    past = now - timedelta(seconds=120)
    header = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert handler.parse_retry_after(header, now=now) == pytest.approx(0.0)


@pytest.mark.parametrize("header", [None, "", "   ", "not-a-date", "12.5.6"])
def test_parse_retry_after_malformed_returns_none(header: str | None) -> None:
    handler = make_handler()
    assert handler.parse_retry_after(header) is None


def test_next_delay_honours_retry_after_clamped() -> None:
    handler = make_handler(backoff_max=60.0)
    assert handler.next_delay(attempt=0, retry_after_header="10") == pytest.approx(10.0)
    # Retry-After larger than backoff_max is clamped.
    assert handler.next_delay(attempt=0, retry_after_header="600") == pytest.approx(60.0)


def test_next_delay_falls_back_to_jittered_backoff() -> None:
    handler = make_handler(backoff_base=2.0, backoff_max=60.0)
    for _ in range(50):
        delay = handler.next_delay(attempt=3)
        # compute_backoff(3) = 16.0 -> jittered in [0, 16].
        assert 0.0 <= delay <= 16.0


def test_next_delay_result_always_clamped() -> None:
    handler = make_handler(backoff_base=1000.0, backoff_max=5.0)
    for _ in range(50):
        assert handler.next_delay(attempt=5) <= 5.0


def test_should_retry_yields_max_retries_plus_one_total_sends() -> None:
    max_retries = 5
    handler = make_handler(max_retries=max_retries)
    attempts = 0
    # Simulate a driver loop that always receives 429.
    while True:
        attempts += 1  # one send performed
        if not handler.should_retry(attempts_made=attempts):
            break
    assert attempts == max_retries + 1


def test_should_retry_zero_retries() -> None:
    handler = make_handler(max_retries=0)
    # After the single initial send, no retry is allowed.
    assert handler.should_retry(attempts_made=1) is False
