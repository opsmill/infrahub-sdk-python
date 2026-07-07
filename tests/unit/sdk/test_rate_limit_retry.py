"""Client-level tests for transparent HTTP 429 retry on the async and sync clients.

Covers (in later implementation chunks): transparent 429->200 retry, honouring
``Retry-After``, clean ``RateLimitError`` on exhaustion, the disabled path, async/sync
parity, all-paths coverage (regular request, multipart, streaming init), and the E2/X1
multipart body re-read regression. This module currently holds the shared imports/skeleton.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any

import httpx
import pytest

from infrahub_sdk import InfrahubClient, InfrahubClientSync
from infrahub_sdk import client as client_module
from infrahub_sdk.config import Config
from infrahub_sdk.exceptions import RateLimitError
from infrahub_sdk.rate_limit import RateLimitRetryHandler
from infrahub_sdk.types import HTTPMethod

__all__ = [
    "Config",
    "InfrahubClient",
    "InfrahubClientSync",
    "RateLimitError",
    "httpx",
    "pytest",
]

CLIENT_TYPES = ["standard", "sync"]


class ScriptedRequester:
    """A pluggable ``requester``/``sync_requester`` that replays a scripted response sequence.

    Each invocation returns the next pre-built ``httpx.Response`` and increments ``call_count``,
    letting a test assert exactly how many HTTP sends the retry driver performed.
    """

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.call_count = 0

    def _next(self) -> httpx.Response:
        response = self._responses[self.call_count]
        self.call_count += 1
        return response

    def sync_request(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response:
        return self._next()

    async def async_request(
        self,
        url: str,
        method: HTTPMethod,
        headers: dict[str, Any],
        timeout: int,
        payload: dict | None = None,
    ) -> httpx.Response:
        return self._next()


def _patch_driver_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the driver's async/sync sleep with no-op recorders so tests never really wait.

    Returns the list that captures every recorded delay, in call order.
    """
    recorded: list[float] = []

    async def fake_async_sleep(delay: float) -> None:
        recorded.append(delay)

    def fake_sync_sleep(delay: float) -> None:
        recorded.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_async_sleep)
    monkeypatch.setattr(client_module.time, "sleep", fake_sync_sleep)
    return recorded


async def _send_request(
    client_type: str,
    requester: ScriptedRequester,
    url: str = "http://mock/graphql/main",
    max_retries: int | None = None,
) -> httpx.Response:
    """Drive the real ``_request`` path on the selected client with the scripted requester.

    ``max_retries`` overrides ``rate_limit_max_retries`` on the client's ``Config`` when set.
    """
    overrides: dict[str, Any] = {} if max_retries is None else {"rate_limit_max_retries": max_retries}
    if client_type == "standard":
        config = Config(address="http://mock", requester=requester.async_request, **overrides)
        client = InfrahubClient(config=config)
        return await client._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})

    config = Config(address="http://mock", sync_requester=requester.sync_request, **overrides)
    client_sync = InfrahubClientSync(config=config)
    return client_sync._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_retries_429_then_succeeds(client_type: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 followed by a 200 is retried transparently: the 200 is returned after two sends."""
    recorded_sleeps = _patch_driver_sleep(monkeypatch)

    success_payload = {"data": {"result": "success"}}
    requester = ScriptedRequester(
        [
            httpx.Response(status_code=429),
            httpx.Response(status_code=200, json=success_payload),
        ]
    )

    response = await _send_request(client_type=client_type, requester=requester)

    assert response.status_code == 200
    assert response.json() == success_payload
    assert requester.call_count == 2
    assert len(recorded_sleeps) == 1


@pytest.mark.parametrize("status_code", [200, 500])
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_passes_non_429_through_untouched(
    client_type: str, status_code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-429 responses (success or error) are returned on the first send with no retry or wait."""
    recorded_sleeps = _patch_driver_sleep(monkeypatch)

    requester = ScriptedRequester([httpx.Response(status_code=status_code, json={"data": None})])

    response = await _send_request(client_type=client_type, requester=requester)

    assert response.status_code == status_code
    assert requester.call_count == 1
    assert recorded_sleeps == []


@dataclass
class RetryAfterCase:
    """A ``Retry-After`` header form and the inclusive wait window the driver must sleep for.

    ``build_header`` is evaluated at test time so date-relative forms are computed against the
    current clock (the driver parses them against ``datetime.now``).
    """

    name: str
    build_header: Callable[[], str]
    lower: float
    upper: float


# Default ``rate_limit_backoff_max`` is 60.0s, so a ``Retry-After`` above it clamps to 60.0.
RETRY_AFTER_CASES = [
    RetryAfterCase(name="delta-seconds", build_header=lambda: "5", lower=5.0, upper=5.0),
    RetryAfterCase(
        name="http-date",
        build_header=lambda: format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True),
        # A few seconds elapse between building the header and the driver parsing it, so the
        # honoured wait lands just under the 30s interval.
        lower=25.0,
        upper=30.1,
    ),
    RetryAfterCase(name="zero-seconds", build_header=lambda: "0", lower=0.0, upper=0.0),
    RetryAfterCase(
        name="past-date",
        build_header=lambda: format_datetime(datetime.now(timezone.utc) - timedelta(seconds=30), usegmt=True),
        lower=0.0,
        upper=0.0,
    ),
    RetryAfterCase(name="above-max-clamped", build_header=lambda: "120", lower=60.0, upper=60.0),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in RETRY_AFTER_CASES])
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_honours_retry_after(
    client_type: str, case: RetryAfterCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parseable ``Retry-After`` on the 429 dictates the wait (clamped to the backoff ceiling)."""
    recorded_sleeps = _patch_driver_sleep(monkeypatch)

    success_payload = {"data": {"result": "success"}}
    requester = ScriptedRequester(
        [
            httpx.Response(status_code=429, headers={"Retry-After": case.build_header()}),
            httpx.Response(status_code=200, json=success_payload),
        ]
    )

    response = await _send_request(client_type=client_type, requester=requester)

    assert response.status_code == 200
    assert response.json() == success_payload
    assert requester.call_count == 2
    assert len(recorded_sleeps) == 1
    assert case.lower <= recorded_sleeps[0] <= case.upper


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_malformed_retry_after_falls_back_to_backoff(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed ``Retry-After`` is ignored: the driver still retries using computed backoff."""
    recorded_sleeps = _patch_driver_sleep(monkeypatch)

    success_payload = {"data": {"result": "success"}}
    requester = ScriptedRequester(
        [
            httpx.Response(status_code=429, headers={"Retry-After": "not-a-real-header"}),
            httpx.Response(status_code=200, json=success_payload),
        ]
    )

    response = await _send_request(client_type=client_type, requester=requester)

    assert response.status_code == 200
    # The retry still happened despite the unparseable header.
    assert requester.call_count == 2
    assert len(recorded_sleeps) == 1

    # The wait came from jittered exponential backoff for the first retry (attempt=0), not the
    # header, so it lands within ``[0, compute_backoff(0)]`` of a handler built from Config defaults.
    defaults = Config(address="http://mock")
    handler = RateLimitRetryHandler(
        max_retries=defaults.rate_limit_max_retries,
        backoff_base=defaults.rate_limit_backoff_base,
        backoff_max=defaults.rate_limit_backoff_max,
    )
    ceiling = handler.compute_backoff(attempt=0)
    assert 0.0 <= recorded_sleeps[0] <= ceiling


# The driver logs each retry through ``logging.getLogger("infrahub_sdk")`` (client ``self.log``).
_RETRY_LOG_LOGGER = "infrahub_sdk"
# Matches the driver's WARNING format: "Rate limited (HTTP 429) on <url>, retry <n> in <d>s".
_RETRY_LOG_PATTERN = re.compile(r"retry (?P<attempt>\d+) in (?P<delay>[\d.]+)s")


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_exhausts_retries_and_raises_rate_limit_error(
    client_type: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Persistent 429 exhausts the budget: exactly ``max_retries + 1`` sends, then one ``RateLimitError``.

    The raised error carries ``url``/``attempts``/``retry_after`` and chains the terminal
    ``httpx.HTTPStatusError`` as ``__cause__``; one WARNING per retry is logged with the url,
    the attempt number, and the honoured delay.
    """
    recorded_sleeps = _patch_driver_sleep(monkeypatch)

    max_retries = 3
    url = "http://mock/graphql/main"
    # Every send returns a 429 carrying ``Retry-After`` so ``err.retry_after`` is populated. A
    # ``request`` is attached (as a real transport always does) so the driver's terminal
    # ``raise_for_status()`` yields a chainable ``httpx.HTTPStatusError``.
    request = httpx.Request(method="POST", url=url)
    requester = ScriptedRequester(
        [httpx.Response(status_code=429, headers={"Retry-After": "5"}, request=request) for _ in range(max_retries + 1)]
    )

    with (
        caplog.at_level(logging.WARNING, logger=_RETRY_LOG_LOGGER),
        pytest.raises(RateLimitError, match="rate-limited") as exc_info,
    ):
        await _send_request(client_type=client_type, requester=requester, url=url, max_retries=max_retries)

    err = exc_info.value
    # Exactly one send more than the retry budget, and it is reflected on the error.
    assert requester.call_count == max_retries + 1
    assert err.attempts == max_retries + 1
    assert err.url == url
    # ``Retry-After: 5`` was parsed and recorded as the last honoured value.
    assert err.retry_after == pytest.approx(5.0)
    # The terminal 429 was surfaced as an ``httpx.HTTPStatusError`` and chained as the cause.
    assert isinstance(err.__cause__, httpx.HTTPStatusError)

    # One sleep per retry, one WARNING per retry (never on the final, budget-exhausting send).
    assert len(recorded_sleeps) == max_retries

    retry_records = [rec for rec in caplog.records if rec.levelno == logging.WARNING and rec.name == _RETRY_LOG_LOGGER]
    assert len(retry_records) == max_retries

    logged_attempts: list[int] = []
    for record, expected_delay in zip(retry_records, recorded_sleeps, strict=True):
        message = record.getMessage()
        assert url in message
        match = _RETRY_LOG_PATTERN.search(message)
        assert match is not None, message
        logged_attempts.append(int(match.group("attempt")))
        # The logged delay is the same value handed to the (patched) sleep for that retry.
        assert float(match.group("delay")) == pytest.approx(expected_delay, abs=0.01)

    # Retries are logged in order with a monotonically increasing attempt number.
    assert logged_attempts == list(range(1, max_retries + 1))
