"""Client-level tests for transparent HTTP 429 retry on the async and sync clients.

Covers transparent 429->200 retry, honouring ``Retry-After``, ``RateLimitError`` on
exhaustion, the disabled path, async/sync parity, all-paths coverage (regular request,
multipart, streaming init), and the multipart body re-read regression.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from infrahub_sdk import InfrahubClient, InfrahubClientSync
from infrahub_sdk import client as client_module
from infrahub_sdk.config import Config
from infrahub_sdk.exceptions import RateLimitError
from infrahub_sdk.rate_limit import RateLimitRetryHandler
from infrahub_sdk.types import HTTPMethod

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

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


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_exhausts_raises_rate_limit_error_when_response_has_no_request(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exhaustion still raises ``RateLimitError`` when the 429 response carries no ``request``.

    A custom ``requester`` may return a response without an attached ``request``; on that
    response ``raise_for_status()`` raises ``RuntimeError`` rather than ``httpx.HTTPStatusError``.
    The driver must still surface ``RateLimitError`` (never leak the ``RuntimeError``); with no
    chainable transport error, ``__cause__`` is ``None``.
    """
    _patch_driver_sleep(monkeypatch)

    max_retries = 2
    url = "http://mock/graphql/main"
    # No ``request=`` attached, mimicking a hand-built response from a custom requester.
    requester = ScriptedRequester([httpx.Response(status_code=429) for _ in range(max_retries + 1)])

    with pytest.raises(RateLimitError, match="rate-limited") as exc_info:
        await _send_request(client_type=client_type, requester=requester, url=url, max_retries=max_retries)

    err = exc_info.value
    assert requester.call_count == max_retries + 1
    assert err.attempts == max_retries + 1
    assert err.__cause__ is None


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_disabled_surfaces_raw_429_without_retry(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With ``rate_limit_retry_enabled=False`` the driver does ONE send and returns the raw 429.

    The response is returned untouched: no ``RateLimitError`` and no wait.
    """
    recorded_sleeps = _patch_driver_sleep(monkeypatch)

    url = "http://mock/graphql/main"
    requester = ScriptedRequester([httpx.Response(status_code=429)])

    if client_type == "standard":
        config = Config(address="http://mock", requester=requester.async_request, rate_limit_retry_enabled=False)
        client = InfrahubClient(config=config)
        response = await client._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})
    else:
        config = Config(address="http://mock", sync_requester=requester.sync_request, rate_limit_retry_enabled=False)
        client_sync = InfrahubClientSync(config=config)
        response = client_sync._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})

    # Raw 429 returned untouched: single send, no wait, no RateLimitError.
    assert response.status_code == 429
    assert requester.call_count == 1
    assert recorded_sleeps == []


@pytest.mark.parametrize("max_retries", [0, 1, 3])
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_max_retries_controls_attempt_count(
    client_type: str, max_retries: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lowered ``rate_limit_max_retries`` bounds the sends: persistent 429 yields ``max_retries + 1``.

    ``max_retries=0`` means no retries — a single 429 send raises ``RateLimitError`` immediately with
    zero waits.
    """
    recorded_sleeps = _patch_driver_sleep(monkeypatch)

    url = "http://mock/graphql/main"
    request = httpx.Request(method="POST", url=url)
    requester = ScriptedRequester([httpx.Response(status_code=429, request=request) for _ in range(max_retries + 1)])

    with pytest.raises(RateLimitError, match="rate-limited") as exc_info:
        await _send_request(client_type=client_type, requester=requester, url=url, max_retries=max_retries)

    assert requester.call_count == max_retries + 1
    assert exc_info.value.attempts == max_retries + 1
    # One wait per retry (never on the final, budget-exhausting send).
    assert len(recorded_sleeps) == max_retries


@dataclass
class ParityCase:
    """A single 429 sequence driven identically through the async and sync clients.

    ``build_responses`` returns a fresh scripted response list per client so the two runs are
    independent. Every 429 carries ``Retry-After`` so the honoured waits are deterministic (no
    jitter), enabling an exact cross-client wait comparison.
    """

    name: str
    build_responses: Callable[[httpx.Request], list[httpx.Response]]
    max_retries: int
    expected_sends: int
    expected_waits: list[float]
    expect_error: bool


_PARITY_SUCCESS_PAYLOAD = {"data": {"result": "success"}}

PARITY_CASES = [
    ParityCase(
        name="retry-after-then-success",
        build_responses=lambda request: [
            httpx.Response(status_code=429, headers={"Retry-After": "5"}, request=request),
            httpx.Response(status_code=429, headers={"Retry-After": "5"}, request=request),
            httpx.Response(status_code=200, json=_PARITY_SUCCESS_PAYLOAD),
        ],
        max_retries=5,
        expected_sends=3,
        expected_waits=[5.0, 5.0],
        expect_error=False,
    ),
    ParityCase(
        name="retry-after-exhaust",
        build_responses=lambda request: [
            httpx.Response(status_code=429, headers={"Retry-After": "5"}, request=request) for _ in range(4)
        ],
        max_retries=3,
        expected_sends=4,
        expected_waits=[5.0, 5.0, 5.0],
        expect_error=True,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in PARITY_CASES])
async def test_async_sync_parity_on_identical_429_sequence(case: ParityCase, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same 429 sequence yields identical sends, waits, and outcome across both clients.

    Uses a deterministic ``Retry-After``-driven sequence so waits can be compared exactly (rather
    than only within jitter tolerance). Asserts identical send counts, matching outcome (same error
    type or same success status), and identical honoured waits.
    """
    url = "http://mock/graphql/main"
    results: dict[str, dict[str, Any]] = {}

    for client_type in CLIENT_TYPES:
        request = httpx.Request(method="POST", url=url)
        requester = ScriptedRequester(case.build_responses(request))
        recorded_sleeps = _patch_driver_sleep(monkeypatch)
        error_type: type | None = None
        status: int | None = None

        if case.expect_error:
            with pytest.raises(RateLimitError, match="rate-limited") as exc_info:
                await _send_request(client_type=client_type, requester=requester, url=url, max_retries=case.max_retries)
            error_type = type(exc_info.value)
        else:
            response = await _send_request(
                client_type=client_type, requester=requester, url=url, max_retries=case.max_retries
            )
            status = response.status_code

        results[client_type] = {
            "sends": requester.call_count,
            "waits": list(recorded_sleeps),
            "error_type": error_type,
            "status": status,
        }

    standard = results["standard"]
    sync = results["sync"]

    # Identical send counts, matching the expected total.
    assert standard["sends"] == sync["sends"] == case.expected_sends
    # Same outcome: same error type (or same success status).
    assert standard["error_type"] == sync["error_type"]
    assert standard["status"] == sync["status"]
    # Deterministic Retry-After waits are identical across clients and equal to the expected values.
    assert standard["waits"] == pytest.approx(sync["waits"])
    assert standard["waits"] == pytest.approx(case.expected_waits)


# --- Backoff growth and jitter divergence at the driver level --------------------------------
#
# Every retry test above pins the wait with a fixed ``Retry-After``, so ``next_delay`` ignores its
# ``attempt`` argument. A bug that always passed ``attempt=0`` (no exponential growth) would sail
# through the whole suite. The two tests below drive a persistent 429 with NO ``Retry-After`` so the
# wait is driven purely by ``compute_backoff(attempt)``, proving the driver hands an incrementing
# ``attempt`` to ``next_delay`` (growth) and that independent instances jitter differently.


async def _send_no_header_429s(
    client_type: str,
    *,
    max_retries: int,
    backoff_base: float,
    backoff_max: float,
) -> None:
    """Drive a persistent, header-less 429 sequence through ``_request`` until the budget is spent.

    Always raises ``RateLimitError`` (the sequence never yields a 200); callers wrap it in
    ``pytest.raises``. ``backoff_base``/``backoff_max`` are threaded onto the client ``Config`` so
    the recorded waits equal ``compute_backoff(attempt)`` when jitter is neutralised.
    """
    url = "http://mock/graphql/main"
    request = httpx.Request(method="POST", url=url)
    requester = ScriptedRequester([httpx.Response(status_code=429, request=request) for _ in range(max_retries + 1)])
    overrides: dict[str, Any] = {
        "rate_limit_max_retries": max_retries,
        "rate_limit_backoff_base": backoff_base,
        "rate_limit_backoff_max": backoff_max,
    }
    if client_type == "standard":
        config = Config(address="http://mock", requester=requester.async_request, **overrides)
        await InfrahubClient(config=config)._request(
            url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={}
        )
        return
    config = Config(address="http://mock", sync_requester=requester.sync_request, **overrides)
    InfrahubClientSync(config=config)._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_backoff_grows_exponentially_and_clamps(client_type: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Header-less persistent 429s wait on exponential backoff that grows per attempt and clamps.

    Jitter is neutralised (``jittered_delay`` patched to the identity) so each recorded wait equals
    ``compute_backoff(attempt)``. With ``base=1.0`` and ``max=6.0`` the four retry waits are
    ``1, 2, 4, 6`` — doubling until the ceiling clamps the last one. This can only hold if the driver
    passes an incrementing ``attempt`` (0, 1, 2, 3) to ``next_delay``.
    """
    recorded_sleeps = _patch_driver_sleep(monkeypatch)
    # Identity jitter: the recorded wait is exactly the computed backoff ceiling for that attempt.
    monkeypatch.setattr(RateLimitRetryHandler, "jittered_delay", lambda _self, ceiling: ceiling)

    max_retries = 4
    backoff_base = 1.0
    backoff_max = 6.0

    with pytest.raises(RateLimitError, match="rate-limited"):
        await _send_no_header_429s(
            client_type=client_type,
            max_retries=max_retries,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
        )

    # One wait per retry; base * 2**attempt, doubling then clamped to backoff_max.
    assert recorded_sleeps == pytest.approx([1.0, 2.0, 4.0, 6.0])


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_jitter_differs_between_instances(client_type: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two independent clients driven through the same header-less 429 sequence jitter differently.

    With real full jitter (``jittered_delay`` NOT patched), the per-retry waits are random draws in
    ``[0, compute_backoff(attempt)]``. Across four retries an exact match between two independent
    instances is astronomically unlikely, so at least one position must differ.
    """
    max_retries = 4
    backoff_base = 5.0
    backoff_max = 60.0

    runs: list[list[float]] = []
    for _ in range(2):
        recorded_sleeps = _patch_driver_sleep(monkeypatch)
        with pytest.raises(RateLimitError, match="rate-limited"):
            await _send_no_header_429s(
                client_type=client_type,
                max_retries=max_retries,
                backoff_base=backoff_base,
                backoff_max=backoff_max,
            )
        runs.append(list(recorded_sleeps))

    first, second = runs
    # Both instances performed the same number of jittered waits ...
    assert len(first) == len(second) == max_retries
    # ... but real full jitter makes at least one recorded wait diverge between the two instances.
    assert first != second


# --- All-paths coverage and multipart body re-read --------------------------------------------
#
# ``_request_multipart`` and ``_get_streaming`` build their own ``httpx`` client and BYPASS the
# pluggable ``requester``/``sync_requester`` shim used by the tests above, so their 429->200
# sequences are scripted at the httpx transport layer with ``httpx_mock`` (pytest-httpx). The
# regular ``_request`` path is exercised the same way here so all three paths share one idiom.

# A non-empty, multi-line file body large enough that a truncated (unrewound) re-send is obviously
# different from the full payload.
MULTIPART_FILE_CONTENT = b"multipart file body that must survive a 429 retry\n" * 16

ALL_REQUEST_PATHS = ["regular", "multipart", "streaming"]


def _make_client(client_type: str) -> InfrahubClient | InfrahubClientSync:
    """Build a client with no ``requester`` override so real httpx transports (mocked) are used."""
    config = Config(address="http://mock")
    if client_type == "standard":
        return InfrahubClient(config=config)
    return InfrahubClientSync(config=config)


def _build_multipart_files() -> dict[str, Any]:
    """Build an httpx ``files`` mapping with a non-empty, seekable file object."""
    return {"file": ("upload.bin", io.BytesIO(MULTIPART_FILE_CONTENT), "application/octet-stream")}


async def _run_multipart(
    client: InfrahubClient | InfrahubClientSync, url: str, files: dict[str, Any]
) -> httpx.Response:
    """Drive the real ``_request_multipart`` path on either client."""
    if isinstance(client, InfrahubClient):
        return await client._request_multipart(url=url, headers={}, timeout=10, files=files)
    return client._request_multipart(url=url, headers={}, timeout=10, files=files)


async def _drive_path(client_type: str, path: str, url: str) -> int:
    """Drive one request path on the selected client and return the final status code.

    For streaming, the response body is read inside the (async) context manager so the 200 stream
    is fully consumed before the status is returned.
    """
    client = _make_client(client_type)

    if path == "regular":
        if isinstance(client, InfrahubClient):
            response = await client._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})
        else:
            response = client._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})
        return response.status_code

    if path == "multipart":
        response = await _run_multipart(client=client, url=url, files=_build_multipart_files())
        return response.status_code

    # streaming: retry happens on stream INITIATION (the 429 arrives in the headers before body).
    if isinstance(client, InfrahubClient):
        async with client._get_streaming(url=url) as response:
            assert await response.aread() is not None
            return response.status_code
    with client._get_streaming(url=url) as response:
        assert response.read() is not None
        return response.status_code


@pytest.mark.parametrize("path", ALL_REQUEST_PATHS)
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_all_request_paths_retry_429_then_succeed(
    client_type: str, path: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 429->200 sequence is retried transparently on every request path, both clients.

    Covers the regular request, the multipart upload, and streaming initiation. Each must issue
    exactly two transport sends (the retry) and surface the final 200.
    """
    recorded_sleeps = _patch_driver_sleep(monkeypatch)

    url = "http://mock/graphql/main"
    httpx_mock.add_response(status_code=429)
    httpx_mock.add_response(status_code=200, json={"data": {"result": "success"}})

    status = await _drive_path(client_type=client_type, path=path, url=url)

    # The retry fired: the final 200 is surfaced after exactly two transport sends, with one wait.
    assert status == 200
    assert len(httpx_mock.get_requests()) == 2
    assert len(recorded_sleeps) == 1


def _multipart_body_without_boundary(request: httpx.Request) -> bytes:
    """Return the multipart body with the random per-request boundary normalised out.

    httpx generates a fresh random boundary for every multipart send, so two identical payloads
    still differ byte-for-byte in their boundary markers; normalising it lets us compare the actual
    encoded body (headers + file part) across attempts.
    """
    content_type = request.headers["content-type"]
    _, _, boundary = content_type.partition("boundary=")
    return request.content.replace(boundary.encode(), b"__BOUNDARY__")


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_multipart_body_survives_retry(
    client_type: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retried multipart upload re-sends the FULL file body, not a consumed/empty stream.

    Scripts ``429 -> 200`` for a multipart upload carrying non-empty file content, then captures the
    request body the transport received on each attempt. The second attempt must carry the full body
    equal to the first (modulo the random multipart boundary), proving the driver rewinds /
    re-materialises the payload between attempts. Were the rewind removed, the second send would
    stream an already-consumed file object and this test would fail.
    """
    _patch_driver_sleep(monkeypatch)

    url = "http://mock/graphql/main"
    httpx_mock.add_response(status_code=429)
    httpx_mock.add_response(status_code=200, json={"data": {"result": "uploaded"}})

    client = _make_client(client_type)
    response = await _run_multipart(client=client, url=url, files=_build_multipart_files())
    assert response.status_code == 200

    requests = httpx_mock.get_requests()
    assert len(requests) == 2

    first_body = requests[0].content
    second_body = requests[1].content

    # Both attempts carried the full, non-empty file content.
    assert MULTIPART_FILE_CONTENT in first_body
    assert MULTIPART_FILE_CONTENT in second_body

    # Modulo the random per-request boundary, the retried body is byte-for-byte equal to the first.
    assert _multipart_body_without_boundary(requests[0]) == _multipart_body_without_boundary(requests[1])


# --- Direct unit test of the multipart rewind helper -----------------------------------------
#
# ``test_multipart_body_survives_retry`` above passes even if ``_rewind_multipart_files`` is gutted,
# because httpx itself rewinds seekable files before sending. This exercises the SDK's own helper
# directly so a regression that removes its rewind is caught.


class RecordingFile:
    """A minimal seekable file object that records every ``seek`` call (no unittest.mock)."""

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)
        self.seek_calls: list[int] = []

    def read(self) -> bytes:
        return self._buffer.read()

    def tell(self) -> int:
        return self._buffer.tell()

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self.seek_calls.append(offset)
        return self._buffer.seek(offset, whence)


def test_rewind_multipart_files_resets_every_file_object() -> None:
    """``_rewind_multipart_files`` calls ``seek(0)`` on every file object across the shapes used.

    Covers the ``(filename, fileobj)`` and ``(filename, fileobj, content_type)`` tuple shapes plus a
    bare file-object value. Each file is advanced to EOF first; after the rewind every file object
    must be back at position 0. This fails if the helper body is gutted.
    """
    two_tuple = RecordingFile(b"two-tuple body")
    three_tuple = RecordingFile(b"three-tuple body")
    bare = RecordingFile(b"bare body")

    files: dict[str, Any] = {
        "two": ("two.bin", two_tuple),
        "three": ("three.bin", three_tuple, "application/octet-stream"),
        "bare": bare,
    }

    # Advance every file to EOF so a missing rewind would leave a consumed/empty stream.
    for file_obj in (two_tuple, three_tuple, bare):
        assert file_obj.read() != b""
        assert file_obj.tell() != 0

    client_module._rewind_multipart_files(files)

    # Every file object was rewound to the start ...
    for file_obj in (two_tuple, three_tuple, bare):
        assert file_obj.seek_calls == [0]
        assert file_obj.tell() == 0
