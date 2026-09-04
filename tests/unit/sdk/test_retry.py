"""Tests for transient-failure retries (``retry_on_failure``) on the async and sync clients.

Covers the ``TransientRetryHandler`` decision logic (classification, backoff, budget), the
transport-level driver in ``_request`` (connection errors, timeouts, transient HTTP statuses),
the GraphQL-envelope retries in ``execute_graphql`` sharing one budget with the transport layer,
the opt-in default, budget exhaustion, unlimited mode, log escalation and configuration plumbing.
"""

from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, BinaryIO

import httpx
import pytest
from pydantic import ValidationError

from infrahub_sdk import InfrahubClient, InfrahubClientSync
from infrahub_sdk import client as client_module
from infrahub_sdk.config import Config
from infrahub_sdk.exceptions import GraphQLError, ServerNotReachableError, ServerNotResponsiveError
from infrahub_sdk.retry import ESCALATE_AFTER_SECONDS, TransientRetryHandler
from infrahub_sdk.types import HTTPMethod

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

CLIENT_TYPES = ["standard", "sync"]
GRAPHQL_URL = "http://mock/graphql/main"
QUERY = "query { InfraDevice { edges { node { id } } } }"
LOGGER_NAME = "infrahub_sdk"


class FakeClock:
    """Deterministic monotonic clock advanced explicitly or by the patched sleeps."""

    def __init__(self, now: float = 1000.0, step: float = 0.0) -> None:
        self.now = now
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ScriptedRequester:
    """A pluggable ``requester``/``sync_requester`` replaying scripted responses or exceptions.

    Each send returns the next ``httpx.Response``, or raises the next exception, and increments
    ``call_count`` so a test can assert exactly how many HTTP sends were performed.
    """

    def __init__(self, steps: Sequence[httpx.Response | Exception]) -> None:
        self._steps = list(steps)
        self.call_count = 0

    def _next(self) -> httpx.Response:
        step = self._steps[self.call_count]
        self.call_count += 1
        if isinstance(step, Exception):
            raise step
        return step

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


def _patch_sleep(monkeypatch: pytest.MonkeyPatch, clock: FakeClock | None = None) -> list[float]:
    """Replace async/sync sleep with recorders that never wait; advance ``clock`` by each delay."""
    recorded: list[float] = []

    def record(delay: float) -> None:
        recorded.append(delay)
        if clock is not None:
            clock.advance(delay)

    async def fake_async_sleep(delay: float) -> None:
        record(delay)

    def fake_sync_sleep(delay: float) -> None:
        record(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_async_sleep)
    monkeypatch.setattr(time, "sleep", fake_sync_sleep)
    return recorded


def _no_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make delays deterministic: the jittered delay becomes the backoff ceiling itself."""
    monkeypatch.setattr(TransientRetryHandler, "jittered_delay", lambda _self, ceiling: ceiling)


def _build_client(
    client_type: str,
    requester: ScriptedRequester,
    clock: FakeClock | None = None,
    **overrides: bool | int | list[int],
) -> InfrahubClient | InfrahubClientSync:
    config_kwargs: dict[str, Any] = dict(overrides)
    client: InfrahubClient | InfrahubClientSync
    if client_type == "standard":
        client = InfrahubClient(
            config=Config(address="http://mock", requester=requester.async_request, **config_kwargs)
        )
    else:
        client = InfrahubClientSync(
            config=Config(address="http://mock", sync_requester=requester.sync_request, **config_kwargs)
        )
    if clock is not None:
        client._retry_handler.clock = clock
    return client


def _build_client_over_httpx(client_type: str, **overrides: bool | int) -> InfrahubClient | InfrahubClientSync:
    """Build a client without a custom requester, so requests go through httpx and its exceptions."""
    config_kwargs: dict[str, Any] = dict(overrides)
    if client_type == "standard":
        return InfrahubClient(config=Config(address="http://mock", **config_kwargs))
    return InfrahubClientSync(config=Config(address="http://mock", **config_kwargs))


async def _execute_graphql(client: InfrahubClient | InfrahubClientSync) -> dict:
    if isinstance(client, InfrahubClient):
        return await client.execute_graphql(query=QUERY)
    return client.execute_graphql(query=QUERY)


async def _request(client: InfrahubClient | InfrahubClientSync, url: str = GRAPHQL_URL) -> httpx.Response:
    if isinstance(client, InfrahubClient):
        return await client._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})
    return client._request(url=url, method=HTTPMethod.POST, headers={}, timeout=10, payload={})


def _response(status_code: int, json: dict | None = None) -> httpx.Response:
    """Build a response with a request attached so ``raise_for_status`` works on it."""
    return httpx.Response(status_code=status_code, json=json, request=httpx.Request("POST", GRAPHQL_URL))


def _ok(data: dict | None = None) -> httpx.Response:
    return _response(200, json={"data": data or {"result": "ok"}})


def _graphql_errors(*errors: dict, status_code: int = 200) -> httpx.Response:
    return _response(status_code, json={"data": None, "errors": list(errors)})


def _transient_error(status: int = 503, message: str = "Unable to connect to the database") -> dict:
    return {"message": message, "extensions": {"code": "DATABASE_UNAVAILABLE", "http_status": status}}


def _connection_error() -> ServerNotReachableError:
    return ServerNotReachableError(address="http://mock")


def _timeout() -> ServerNotResponsiveError:
    return ServerNotResponsiveError(url=GRAPHQL_URL, timeout=10)


def _handler(**overrides: bool | float | list[int] | FakeClock) -> TransientRetryHandler:
    params: dict[str, Any] = {"enabled": True, "base_delay": 5, "max_delay": 60, "max_duration": 300}
    params.update(overrides)
    return TransientRetryHandler(**params)


# --- Handler decision logic -------------------------------------------------------------------------


@dataclass
class StatusCase:
    name: str
    status: int
    expected: bool


STATUS_CASES = [
    StatusCase(name="502", status=502, expected=True),
    StatusCase(name="503", status=503, expected=True),
    StatusCase(name="504", status=504, expected=True),
    StatusCase(name="500-unclassified-server-error", status=500, expected=True),
    StatusCase(name="429-has-its-own-handler", status=429, expected=False),
    StatusCase(name="400", status=400, expected=False),
    StatusCase(name="200", status=200, expected=False),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in STATUS_CASES])
def test_handler_default_transient_statuses(case: StatusCase) -> None:
    assert _handler().is_transient_status(case.status) is case.expected


def test_handler_custom_status_codes_replace_the_default_set() -> None:
    handler = _handler(status_codes=[500, 503])
    assert handler.is_transient_status(500)
    assert handler.is_transient_status(503)
    assert not handler.is_transient_status(502)


@dataclass
class GraphQLErrorsCase:
    name: str
    errors: Any
    expected: bool


GRAPHQL_ERRORS_CASES = [
    GraphQLErrorsCase(name="graphql-http-status", errors=[_transient_error(503)], expected=True),
    GraphQLErrorsCase(name="all-transient", errors=[_transient_error(502), _transient_error(504)], expected=True),
    GraphQLErrorsCase(
        name="rest-integer-code", errors=[{"message": "db down", "extensions": {"code": 503}}], expected=True
    ),
    GraphQLErrorsCase(
        name="one-unclassified", errors=[_transient_error(503), {"message": "Unknown field"}], expected=False
    ),
    GraphQLErrorsCase(
        name="non-transient-status",
        errors=[{"message": "not found", "extensions": {"code": "NODE_NOT_FOUND", "http_status": 404}}],
        expected=False,
    ),
    GraphQLErrorsCase(
        name="bool-is-not-a-status", errors=[{"message": "x", "extensions": {"code": True}}], expected=False
    ),
    GraphQLErrorsCase(name="malformed-extensions", errors=[{"message": "x", "extensions": "oops"}], expected=False),
    GraphQLErrorsCase(name="malformed-error", errors=["not a dict"], expected=False),
    GraphQLErrorsCase(name="empty", errors=[], expected=False),
    GraphQLErrorsCase(name="none", errors=None, expected=False),
    GraphQLErrorsCase(name="not-a-list", errors="errors", expected=False),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in GRAPHQL_ERRORS_CASES])
def test_handler_graphql_error_classification(case: GraphQLErrorsCase) -> None:
    assert _handler().is_transient_graphql_errors(case.errors) is case.expected


def test_handler_graphql_error_status_prefers_http_status_over_code() -> None:
    error = {"message": "x", "extensions": {"code": 200, "http_status": 503}}
    assert TransientRetryHandler.graphql_error_status(error) == 503


def test_handler_describe_graphql_errors_mentions_status_message_and_count() -> None:
    description = TransientRetryHandler.describe_graphql_errors(
        [_transient_error(503, "db down"), _transient_error(502)]
    )
    assert description == "GraphQL error with HTTP status 503: db down (+1 more)"


def test_handler_backoff_doubles_from_base_delay_and_clamps() -> None:
    handler = _handler(base_delay=5, max_delay=60)
    assert [handler.compute_backoff(attempt) for attempt in range(1, 7)] == [5, 10, 20, 40, 60, 60]
    assert handler.compute_backoff(0) == 5
    assert handler.compute_backoff(10_000) == 60


def test_handler_jitter_stays_within_half_to_full_ceiling() -> None:
    handler = _handler()
    for _ in range(200):
        assert 30 <= handler.jittered_delay(60) <= 60


def test_handler_budget_is_time_based() -> None:
    clock = FakeClock()
    handler = _handler(max_duration=10, clock=clock)
    state = handler.new_state()

    assert not handler.unlimited
    assert handler.should_retry(state)
    assert handler.remaining(state) == 10
    clock.advance(9.9)
    assert handler.should_retry(state)
    clock.advance(0.1)
    assert not handler.should_retry(state)
    assert handler.remaining(state) == 0


def test_handler_zero_duration_means_unlimited() -> None:
    clock = FakeClock()
    handler = _handler(max_duration=0, clock=clock)
    state = handler.new_state()

    assert handler.unlimited
    assert handler.remaining(state) is None
    clock.advance(10**6)
    assert handler.should_retry(state)


def test_handler_disabled_never_retries() -> None:
    handler = _handler(enabled=False)
    assert not handler.should_retry(handler.new_state())


def test_handler_next_delay_never_sleeps_past_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_jitter(monkeypatch)
    clock = FakeClock()
    handler = _handler(max_duration=12, clock=clock)
    state = handler.new_state()

    state.attempts = 3  # backoff ceiling would be 20s
    assert handler.next_delay(state) == 12
    clock.advance(10)
    assert handler.next_delay(state) == 2


def test_handler_retry_log_escalates_to_error_after_threshold(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _no_jitter(monkeypatch)
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    clock = FakeClock()
    handler = _handler(max_duration=0, clock=clock)
    state = handler.new_state()

    handler.prepare_retry(state=state, url=GRAPHQL_URL, reason="HTTP 503")
    clock.advance(ESCALATE_AFTER_SECONDS)
    handler.prepare_retry(state=state, url=GRAPHQL_URL, reason="HTTP 503")

    assert [record.levelno for record in caplog.records] == [logging.WARNING, logging.ERROR]
    assert "Retry 1 in 5.0s (0s elapsed, no time limit)" in caplog.records[0].message
    assert "Retry 2 in 10.0s (300s elapsed, no time limit)" in caplog.records[1].message


# --- Opt-in default ---------------------------------------------------------------------------------


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_disabled_by_default_surfaces_connection_error_immediately(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_sleeps = _patch_sleep(monkeypatch)
    requester = ScriptedRequester([_connection_error(), _ok()])
    client = _build_client(client_type, requester)

    assert client.retry_on_failure is False
    with pytest.raises(ServerNotReachableError, match="Unable to connect to 'http://mock'"):
        await _execute_graphql(client)
    assert requester.call_count == 1
    assert recorded_sleeps == []


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_disabled_by_default_returns_transient_status_untouched(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_sleeps = _patch_sleep(monkeypatch)
    requester = ScriptedRequester([_response(503), _ok()])
    client = _build_client(client_type, requester)

    response = await _request(client)

    assert response.status_code == 503
    assert requester.call_count == 1
    assert recorded_sleeps == []


# --- Transport-level retries ------------------------------------------------------------------------


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_retries_connection_error_and_timeout_then_succeeds(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_jitter(monkeypatch)
    recorded_sleeps = _patch_sleep(monkeypatch)
    requester = ScriptedRequester([_connection_error(), _timeout(), _ok()])
    client = _build_client(client_type, requester, retry_on_failure=True)

    data = await _execute_graphql(client)

    assert data == {"result": "ok"}
    assert requester.call_count == 3
    assert recorded_sleeps == [5, 10]


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_retries_transient_http_statuses_with_growing_backoff(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_jitter(monkeypatch)
    recorded_sleeps = _patch_sleep(monkeypatch)
    requester = ScriptedRequester(
        [
            _response(503),
            _response(502),
            _response(504),
            _ok(),
        ]
    )
    client = _build_client(client_type, requester, retry_on_failure=True)

    response = await _request(client)

    assert response.status_code == 200
    assert requester.call_count == 4
    assert recorded_sleeps == [5, 10, 20]


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_custom_status_codes_control_what_is_transient(client_type: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sleep(monkeypatch)

    default_requester = ScriptedRequester([_response(500), _ok()])
    default_client = _build_client(client_type, default_requester, retry_on_failure=True)
    assert (await _request(default_client)).status_code == 200
    assert default_requester.call_count == 2

    custom_requester = ScriptedRequester([_response(500), _ok()])
    custom_client = _build_client(client_type, custom_requester, retry_on_failure=True, retry_status_codes=[502, 503])
    assert (await _request(custom_client)).status_code == 500
    assert custom_requester.call_count == 1


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_rest_endpoints_are_retried_too(client_type: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``query_gql_query`` (used by generators to collect their data) goes through the same retry path."""
    _patch_sleep(monkeypatch)
    payload: dict[str, Any] = {"data": {"InfraDevice": {"edges": []}}}
    requester = ScriptedRequester([_connection_error(), _response(200, json=payload)])
    client = _build_client(client_type, requester, retry_on_failure=True)

    if isinstance(client, InfrahubClient):
        result = await client.query_gql_query(name="my_query")
    else:
        result = client.query_gql_query(name="my_query")

    assert result == payload
    assert requester.call_count == 2


# --- Lost connections, whichever way httpx reports them ----------------------------------------------


@dataclass
class LostConnectionCase:
    name: str
    exception: Exception


LOST_CONNECTION_CASES = [
    LostConnectionCase(name="refused", exception=httpx.ConnectError("connection refused")),
    LostConnectionCase(name="reset", exception=httpx.ReadError("connection reset by peer")),
    LostConnectionCase(
        name="disconnected-mid-request",
        exception=httpx.RemoteProtocolError("Server disconnected without sending a response."),
    ),
]


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in LOST_CONNECTION_CASES])
async def test_lost_connection_is_transient_whichever_httpx_error_reports_it(
    client_type: str, case: LostConnectionCase, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Losing the connection before a response arrives is transient however httpx classifies it.

    ``RemoteProtocolError`` is the shape a failover takes on a request that is already in flight:
    the server or the load balancer in front of it closes the socket before sending a single byte
    of the response. httpx reports that as a protocol error rather than a network error, so it
    only reaches the retry handler if the client maps it too.
    """
    _no_jitter(monkeypatch)
    recorded_sleeps = _patch_sleep(monkeypatch)
    httpx_mock.add_exception(case.exception, url=GRAPHQL_URL)
    httpx_mock.add_response(url=GRAPHQL_URL, json={"data": {"result": "ok"}})
    client = _build_client_over_httpx(client_type, retry_on_failure=True)

    assert await _execute_graphql(client) == {"result": "ok"}
    assert recorded_sleeps == [5]


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in LOST_CONNECTION_CASES])
async def test_lost_connection_surfaces_as_unreachable_when_retries_are_disabled(
    client_type: str, case: LostConnectionCase, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_exception(case.exception, url=GRAPHQL_URL)
    client = _build_client_over_httpx(client_type, retry_on_failure=False)

    with pytest.raises(ServerNotReachableError, match="Unable to connect to 'http://mock'"):
        await _execute_graphql(client)


# --- GraphQL-envelope retries -----------------------------------------------------------------------


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_retries_transient_graphql_errors(
    client_type: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _no_jitter(monkeypatch)
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    recorded_sleeps = _patch_sleep(monkeypatch)
    requester = ScriptedRequester(
        [
            _graphql_errors(_transient_error(503, "Unable to connect to the database")),
            _graphql_errors(_transient_error(502), _transient_error(504)),
            _ok(),
        ]
    )
    client = _build_client(client_type, requester, retry_on_failure=True)

    data = await _execute_graphql(client)

    assert data == {"result": "ok"}
    assert requester.call_count == 3
    assert recorded_sleeps == [5, 10]
    assert "GraphQL error with HTTP status 503: Unable to connect to the database" in caplog.text


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_graphql_and_transport_retries_share_one_attempt_counter(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backoff keeps growing across layers: the envelope retry does not restart from the base delay."""
    _no_jitter(monkeypatch)
    recorded_sleeps = _patch_sleep(monkeypatch)
    requester = ScriptedRequester(
        [
            _response(503),
            _graphql_errors(_transient_error(503)),
            _connection_error(),
            _ok(),
        ]
    )
    client = _build_client(client_type, requester, retry_on_failure=True)

    data = await _execute_graphql(client)

    assert data == {"result": "ok"}
    assert requester.call_count == 4
    assert recorded_sleeps == [5, 10, 20]


@dataclass
class NonTransientCase:
    name: str
    errors: list[dict]


NON_TRANSIENT_CASES = [
    NonTransientCase(
        name="non-transient-status",
        errors=[{"message": "Unknown field", "extensions": {"code": "GRAPHQL_VALIDATION", "http_status": 400}}],
    ),
    NonTransientCase(name="mixed", errors=[_transient_error(503), {"message": "Unknown field"}]),
    NonTransientCase(name="unclassified", errors=[{"message": "legacy error without extensions"}]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in NON_TRANSIENT_CASES])
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_non_transient_graphql_errors_raise_immediately(
    client_type: str, case: NonTransientCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_sleeps = _patch_sleep(monkeypatch)
    requester = ScriptedRequester([_graphql_errors(*case.errors), _ok()])
    client = _build_client(client_type, requester, retry_on_failure=True, max_retry_duration=0)

    with pytest.raises(GraphQLError, match="An error occurred while executing the GraphQL Query") as exc:
        await _execute_graphql(client)

    assert exc.value.errors == case.errors
    assert requester.call_count == 1
    assert recorded_sleeps == []


# --- Budget exhaustion and unlimited mode -----------------------------------------------------------


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_budget_exhaustion_reraises_the_original_exception(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_jitter(monkeypatch)
    clock = FakeClock()
    recorded_sleeps = _patch_sleep(monkeypatch, clock=clock)
    requester = ScriptedRequester([_timeout() for _ in range(10)])
    client = _build_client(client_type, requester, clock=clock, retry_on_failure=True, max_retry_duration=12)

    with pytest.raises(ServerNotResponsiveError, match="Unable to read from"):
        await _execute_graphql(client)

    # 5s, then 10s clamped to the 7s left in the budget, then the budget is spent.
    assert recorded_sleeps == [5, 7]
    assert requester.call_count == 3


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_budget_exhaustion_on_transient_status_returns_last_response(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_jitter(monkeypatch)
    clock = FakeClock()
    _patch_sleep(monkeypatch, clock=clock)
    requester = ScriptedRequester([_response(503) for _ in range(10)])
    client = _build_client(client_type, requester, clock=clock, retry_on_failure=True, max_retry_duration=12)

    response = await _request(client)

    assert response.status_code == 503
    assert requester.call_count == 3


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_budget_exhaustion_on_5xx_graphql_envelope_raises_graphql_error(
    client_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once the shared budget is spent, ``execute_graphql`` does not start a second one for the envelope."""
    _no_jitter(monkeypatch)
    clock = FakeClock()
    recorded_sleeps = _patch_sleep(monkeypatch, clock=clock)
    envelope = {"message": "Service unavailable", "extensions": {"code": 503}}
    requester = ScriptedRequester([_graphql_errors(envelope, status_code=503) for _ in range(10)])
    client = _build_client(client_type, requester, clock=clock, retry_on_failure=True, max_retry_duration=12)

    with pytest.raises(GraphQLError, match="An error occurred while executing the GraphQL Query") as exc:
        await _execute_graphql(client)

    assert exc.value.errors == [envelope]
    assert requester.call_count == 3
    assert recorded_sleeps == [5, 7]


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_unlimited_budget_keeps_retrying_and_escalates_logging(
    client_type: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _no_jitter(monkeypatch)
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)
    clock = FakeClock()
    recorded_sleeps = _patch_sleep(monkeypatch, clock=clock)
    failures = 40
    requester = ScriptedRequester([_connection_error() for _ in range(failures)] + [_ok()])
    client = _build_client(client_type, requester, clock=clock, retry_on_failure=True, max_retry_duration=0)

    data = await _execute_graphql(client)

    assert data == {"result": "ok"}
    assert requester.call_count == failures + 1
    assert len(recorded_sleeps) == failures
    assert recorded_sleeps[:5] == [5, 10, 20, 40, 60]
    assert max(recorded_sleeps) == 60
    assert clock.now - 1000.0 > ESCALATE_AFTER_SECONDS
    levels = {record.levelno for record in caplog.records}
    assert levels == {logging.WARNING, logging.ERROR}
    assert "no time limit" in caplog.records[-1].message


# --- Runtime toggling and configuration -------------------------------------------------------------


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_retry_settings_can_be_toggled_at_runtime(client_type: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_jitter(monkeypatch)
    recorded_sleeps = _patch_sleep(monkeypatch)
    requester = ScriptedRequester([_connection_error(), _ok()])
    client = _build_client(client_type, requester)
    assert client.retry_delay == 5

    client.retry_on_failure = True
    client.retry_delay = 1

    data = await _execute_graphql(client)

    assert data == {"result": "ok"}
    assert recorded_sleeps == [1]


def test_config_wires_the_retry_handler() -> None:
    config = Config(
        address="http://mock",
        retry_on_failure=True,
        retry_delay=2,
        retry_max_delay=30,
        max_retry_duration=0,
        retry_status_codes=[500, 503],
    )
    handler = InfrahubClient(config=config)._retry_handler

    assert handler.enabled is True
    assert handler.base_delay == 2
    assert handler.max_delay == 30
    assert handler.unlimited
    assert handler.status_codes == frozenset({500, 503})


def test_config_defaults_keep_retries_opt_in() -> None:
    config = Config(address="http://mock")

    assert config.retry_on_failure is False
    assert config.retry_delay == 5
    assert config.retry_max_delay == 60
    assert config.max_retry_duration == 300
    assert config.retry_status_codes == [500, 502, 503, 504]


@pytest.mark.parametrize("field", ["retry_delay", "retry_max_delay", "max_retry_duration"])
def test_config_rejects_negative_retry_settings(field: str) -> None:
    overrides: dict[str, Any] = {field: -1}
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Config(address="http://mock", **overrides)


def test_config_reads_retry_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFRAHUB_RETRY_ON_FAILURE", "true")
    monkeypatch.setenv("INFRAHUB_MAX_RETRY_DURATION", "0")
    monkeypatch.setenv("INFRAHUB_RETRY_STATUS_CODES", "[503, 504]")

    config = Config(address="http://mock")

    assert config.retry_on_failure is True
    assert config.max_retry_duration == 0
    assert config.retry_status_codes == [503, 504]


# --- Every request path: multipart uploads and streamed downloads ------------------------------------

ALL_REQUEST_PATHS = ["regular", "multipart", "streaming"]
MULTIPART_FILE_CONTENT = b"multipart file body that must survive a transient retry\n" * 8
UPLOAD_MUTATION = "mutation ($file: Upload!) { InfrahubObjectUpload(data: { file: $file }) { ok } }"


class NonSeekableStream(io.BytesIO):
    """A read-only stream that cannot be rewound, like a pipe or an HTTP body."""

    def seekable(self) -> bool:
        return False

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        raise io.UnsupportedOperation("seek")

    def tell(self) -> int:
        raise io.UnsupportedOperation("tell")


def _multipart_files() -> dict[str, Any]:
    return {"file": ("upload.bin", io.BytesIO(MULTIPART_FILE_CONTENT), "application/octet-stream")}


async def _drive_path(client: InfrahubClient | InfrahubClientSync, path: str) -> int:
    """Drive one request path and return the final status; a streamed body is read inside its context."""
    if path == "regular":
        return (await _request(client)).status_code
    if path == "multipart":
        if isinstance(client, InfrahubClient):
            response = await client._request_multipart(
                url=GRAPHQL_URL, headers={}, timeout=10, files=_multipart_files()
            )
        else:
            response = client._request_multipart(url=GRAPHQL_URL, headers={}, timeout=10, files=_multipart_files())
        return response.status_code
    if isinstance(client, InfrahubClient):
        async with client._get_streaming(url=GRAPHQL_URL) as response:
            await response.aread()
            return response.status_code
    with client._get_streaming(url=GRAPHQL_URL) as response:
        response.read()
        return response.status_code


async def _upload(client: InfrahubClient | InfrahubClientSync, file_content: BinaryIO) -> dict:
    if isinstance(client, InfrahubClient):
        return await client._execute_graphql_with_file(
            query=UPLOAD_MUTATION, variables={}, file_content=file_content, file_name="upload.bin"
        )
    return client._execute_graphql_with_file(
        query=UPLOAD_MUTATION, variables={}, file_content=file_content, file_name="upload.bin"
    )


@pytest.mark.parametrize("path", ALL_REQUEST_PATHS)
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_all_request_paths_retry_transient_status_then_succeed(
    client_type: str, path: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_sleeps = _patch_sleep(monkeypatch)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200, json={"data": {"result": "success"}})
    client = _build_client_over_httpx(client_type, retry_on_failure=True)

    status = await _drive_path(client, path)

    assert status == 200
    assert len(httpx_mock.get_requests()) == 2
    assert len(recorded_sleeps) == 1


@pytest.mark.parametrize("path", ALL_REQUEST_PATHS)
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_all_request_paths_retry_lost_connection_then_succeed(
    client_type: str, path: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_sleeps = _patch_sleep(monkeypatch)
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    httpx_mock.add_response(status_code=200, json={"data": {"result": "success"}})
    client = _build_client_over_httpx(client_type, retry_on_failure=True)

    status = await _drive_path(client, path)

    assert status == 200
    assert len(httpx_mock.get_requests()) == 2
    assert len(recorded_sleeps) == 1


@pytest.mark.parametrize("path", ALL_REQUEST_PATHS)
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_all_request_paths_pass_transient_status_through_when_disabled(
    client_type: str, path: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_sleeps = _patch_sleep(monkeypatch)
    httpx_mock.add_response(status_code=503, content=b"upstream unavailable")
    client = _build_client_over_httpx(client_type)

    status = await _drive_path(client, path)

    assert status == 503
    assert len(httpx_mock.get_requests()) == 1
    assert recorded_sleeps == []


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_multipart_mutation_retries_transient_graphql_errors_on_the_shared_budget(
    client_type: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient status and then a transient GraphQL envelope are retried on one attempt counter, re-sending the file."""
    _no_jitter(monkeypatch)
    recorded_sleeps = _patch_sleep(monkeypatch)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200, json={"data": None, "errors": [_transient_error(503)]})
    httpx_mock.add_response(status_code=200, json={"data": {"InfrahubObjectUpload": {"ok": True}}})
    client = _build_client_over_httpx(client_type, retry_on_failure=True)

    data = await _upload(client, io.BytesIO(MULTIPART_FILE_CONTENT))

    assert data == {"InfrahubObjectUpload": {"ok": True}}
    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    assert recorded_sleeps == [5, 10]
    assert all(MULTIPART_FILE_CONTENT in request.content for request in requests)


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_multipart_mutation_raises_non_transient_graphql_errors_immediately(
    client_type: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded_sleeps = _patch_sleep(monkeypatch)
    errors = [{"message": "Unknown field", "extensions": {"code": "GRAPHQL_VALIDATION", "http_status": 400}}]
    httpx_mock.add_response(status_code=200, json={"data": None, "errors": errors})
    client = _build_client_over_httpx(client_type, retry_on_failure=True, max_retry_duration=0)

    with pytest.raises(GraphQLError, match="An error occurred while executing the GraphQL Query") as exc:
        await _upload(client, io.BytesIO(MULTIPART_FILE_CONTENT))

    assert exc.value.errors == errors
    assert len(httpx_mock.get_requests()) == 1
    assert recorded_sleeps == []


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_multipart_retry_re_sends_a_non_seekable_upload_in_full(
    client_type: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream that cannot be rewound is copied once, so the transport and envelope retries still carry the body."""
    _patch_sleep(monkeypatch)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200, json={"data": None, "errors": [_transient_error(503)]})
    httpx_mock.add_response(status_code=200, json={"data": {"InfrahubObjectUpload": {"ok": True}}})
    client = _build_client_over_httpx(client_type, retry_on_failure=True)

    data = await _upload(client, NonSeekableStream(MULTIPART_FILE_CONTENT))

    assert data == {"InfrahubObjectUpload": {"ok": True}}
    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    assert all(MULTIPART_FILE_CONTENT in request.content for request in requests)


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_streaming_hands_over_an_open_transient_response_once_the_budget_is_spent(
    client_type: str, httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient status the handler will not retry is not pre-read: the caller gets the stream untouched."""
    recorded_sleeps = _patch_sleep(monkeypatch)
    httpx_mock.add_response(status_code=503, content=b"upstream unavailable")
    client = _build_client_over_httpx(client_type, retry_on_failure=True, max_retry_duration=1)
    client._retry_handler.clock = FakeClock(step=1.0)  # every look at the clock moves it past the budget

    if isinstance(client, InfrahubClient):
        async with client._get_streaming(url=GRAPHQL_URL) as response:
            assert response.status_code == 503
            assert not response.is_stream_consumed
            assert await response.aread() == b"upstream unavailable"
    else:
        with client._get_streaming(url=GRAPHQL_URL) as sync_response:
            assert sync_response.status_code == 503
            assert not sync_response.is_stream_consumed
            assert sync_response.read() == b"upstream unavailable"

    assert len(httpx_mock.get_requests()) == 1
    assert recorded_sleeps == []


async def test_async_upload_copies_a_non_seekable_stream_off_the_event_loop(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Draining a stream that cannot be rewound is blocking I/O, so the async client hands it to a worker thread."""
    offloaded: list[str] = []
    real_to_thread = asyncio.to_thread

    async def recording_to_thread(func: Callable[..., object], /, *args: object, **kwargs: object) -> object:
        offloaded.append(getattr(func, "__name__", repr(func)))
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", recording_to_thread)
    httpx_mock.add_response(status_code=200, json={"data": {"InfrahubObjectUpload": {"ok": True}}})
    client = _build_client_over_httpx("standard")

    data = await _upload(client, NonSeekableStream(MULTIPART_FILE_CONTENT))

    assert data == {"InfrahubObjectUpload": {"ok": True}}
    assert len(offloaded) == 1, f"expected exactly the stream copy to be offloaded, got {offloaded}"
    assert MULTIPART_FILE_CONTENT in httpx_mock.get_requests()[0].content


async def test_cancelled_async_upload_waits_for_the_stream_copy_before_closing_the_buffer() -> None:
    """Cancelling mid-copy must not close the temporary file under the worker thread still filling it."""
    started = threading.Event()
    release = threading.Event()
    reads: list[bytes] = []

    class BlockingStream(NonSeekableStream):
        def read(self, size: int | None = -1) -> bytes:
            started.set()
            assert release.wait(timeout=5), "the test never released the copy"
            chunk = super().read(size)
            reads.append(chunk)
            return chunk

    async def upload() -> None:
        async with client_module._aseekable_upload(BlockingStream(MULTIPART_FILE_CONTENT)):
            pytest.fail("the upload body should never run once cancelled during the copy")

    task = asyncio.create_task(upload())
    assert await asyncio.to_thread(started.wait, 5), "the copy never started"  # the worker is now blocked mid-copy

    task.cancel()
    await asyncio.sleep(0.05)
    assert not task.done(), "the cancellation surfaced while the worker thread was still copying"

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert reads[-1] == b"", "the copy should have drained the stream to EOF before the cancellation surfaced"
