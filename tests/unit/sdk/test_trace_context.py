from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import opentelemetry
import pytest
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, use_span

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

TRACE_ID = 0x0AF7651916CD43DD8448EB211C80319C
SPAN_ID = 0xB7AD6B7169203331
EXPECTED_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
QUERY = "query { InfrahubInfo { version } }"

client_types = ["standard", "sync"]


def _span() -> NonRecordingSpan:
    return NonRecordingSpan(
        SpanContext(trace_id=TRACE_ID, span_id=SPAN_ID, is_remote=False, trace_flags=TraceFlags(TraceFlags.SAMPLED))
    )


async def _execute(client_type: str) -> None:
    config = Config(address="http://mock", api_token="token")
    if client_type == "standard":
        await InfrahubClient(config=config).execute_graphql(query=QUERY)
    else:
        InfrahubClientSync(config=config).execute_graphql(query=QUERY)


@pytest.fixture
def graphql_response(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {"InfrahubInfo": {"version": "1"}}},
        is_reusable=True,
    )
    return httpx_mock


@pytest.mark.parametrize("client_type", client_types)
async def test_request_inside_a_span_carries_its_traceparent(client_type: str, graphql_response: HTTPXMock) -> None:
    with use_span(_span()):
        await _execute(client_type)

    request = graphql_response.get_request()
    assert request is not None
    assert request.headers["traceparent"] == EXPECTED_TRACEPARENT


@pytest.mark.parametrize("client_type", client_types)
async def test_request_outside_a_span_has_no_traceparent(client_type: str, graphql_response: HTTPXMock) -> None:
    await _execute(client_type)

    request = graphql_response.get_request()
    assert request is not None
    assert "traceparent" not in request.headers


@pytest.mark.parametrize("client_type", client_types)
async def test_request_without_opentelemetry_has_no_traceparent(
    client_type: str, graphql_response: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    span = _span()
    monkeypatch.setitem(sys.modules, "opentelemetry", None)

    with use_span(span):
        await _execute(client_type)

    request = graphql_response.get_request()
    assert request is not None
    assert "traceparent" not in request.headers


@pytest.mark.parametrize("client_type", client_types)
async def test_invalid_propagator_setting_sends_no_traceparent_and_warns_once(
    client_type: str, graphql_response: HTTPXMock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    propagator = f"not-a-propagator-{client_type}"
    monkeypatch.setenv("OTEL_PROPAGATORS", propagator)
    monkeypatch.delitem(sys.modules, "opentelemetry.propagate", raising=False)
    monkeypatch.delattr(opentelemetry, "propagate", raising=False)

    with use_span(_span()), caplog.at_level("WARNING", logger="infrahub_sdk"):
        await _execute(client_type)
        await _execute(client_type)

    requests = graphql_response.get_requests()
    assert len(requests) == 2
    assert all("traceparent" not in request.headers for request in requests)
    expected = (
        "Not sending the trace context: OpenTelemetry could not load its propagators "
        f"(Propagator {propagator} not found. It is either misspelled or not installed.)"
    )
    assert [record.getMessage() for record in caplog.records if "trace context" in record.getMessage()] == [expected]
