from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.troubleshooting import app

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

runner = CliRunner()

URL = "http://mock/api/troubleshooting/trace-sample-ratio"
TRACING_OFF_MESSAGE = "Tracing is not enabled on this instance; set INFRAHUB_TRACE_ENABLE"

TEMPORARY_STATE = {
    "enabled": True,
    "default_ratio": 0.1,
    "temporary_ratio": 1.0,
    "expires_at": "2026-10-22T12:00:00Z",
    "ratio_in_force": 1.0,
}
DEFAULT_STATE = {
    "enabled": True,
    "default_ratio": 0.1,
    "temporary_ratio": None,
    "expires_at": None,
    "ratio_in_force": 0.1,
}
TRACING_OFF_ERROR = {"data": None, "errors": [{"message": TRACING_OFF_MESSAGE, "extensions": {"code": 400}}]}


def test_get_prints_the_state(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=URL, json=TEMPORARY_STATE)

    result = runner.invoke(app=app, args=["trace-sample-ratio", "get"])

    assert result.exit_code == 0, result.stdout
    assert "Ratio in force" in result.stdout
    assert "2026-10-22T12:00:00Z" in result.stdout


def test_get_when_tracing_is_off_says_so(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=URL, json={"enabled": False})

    result = runner.invoke(app=app, args=["trace-sample-ratio", "get"])

    assert result.exit_code == 0, result.stdout
    assert "Tracing enabled" in result.stdout
    assert "False" in result.stdout


def test_set_sends_the_ratio_and_the_duration(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=URL, json=TEMPORARY_STATE)

    result = runner.invoke(app=app, args=["trace-sample-ratio", "set", "--ratio", "1", "--duration", "3600"])

    assert result.exit_code == 0, result.stdout
    request = httpx_mock.get_request()
    assert request is not None
    assert json.loads(request.content) == {"ratio": 1.0, "duration_seconds": 3600}
    assert "Ratio in force" in result.stdout


def test_clear_sends_a_delete(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="DELETE", url=URL, json=DEFAULT_STATE)

    result = runner.invoke(app=app, args=["trace-sample-ratio", "clear"])

    assert result.exit_code == 0, result.stdout
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "DELETE"


@dataclass
class ServerErrorCase:
    name: str
    method: str
    args: list[str]


SERVER_ERROR_CASES = [
    ServerErrorCase(name="set", method="PUT", args=["trace-sample-ratio", "set", "--ratio", "1", "--duration", "60"]),
    ServerErrorCase(name="clear", method="DELETE", args=["trace-sample-ratio", "clear"]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in SERVER_ERROR_CASES])
def test_server_error_is_printed_unchanged(case: ServerErrorCase, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method=case.method, url=URL, status_code=400, json=TRACING_OFF_ERROR)

    result = runner.invoke(app=app, args=case.args)

    assert result.exit_code == 1
    assert TRACING_OFF_MESSAGE in result.stdout.replace("\n", "")


@dataclass
class InvalidOptionCase:
    name: str
    ratio: str
    duration: str


INVALID_OPTION_CASES = [
    InvalidOptionCase(name="ratio-below-0", ratio="-0.1", duration="60"),
    InvalidOptionCase(name="ratio-above-1", ratio="1.5", duration="60"),
    InvalidOptionCase(name="duration-below-1", ratio="0.5", duration="0"),
    InvalidOptionCase(name="duration-above-24-hours", ratio="0.5", duration="86401"),
    InvalidOptionCase(name="ratio-nan", ratio="nan", duration="60"),
    InvalidOptionCase(name="duration-nan", ratio="0.5", duration="nan"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in INVALID_OPTION_CASES])
def test_set_rejects_values_outside_the_limits_without_a_request(
    case: InvalidOptionCase, httpx_mock: HTTPXMock
) -> None:
    result = runner.invoke(
        app=app, args=["trace-sample-ratio", "set", "--ratio", case.ratio, "--duration", case.duration]
    )

    assert result.exit_code == 2
    assert httpx_mock.get_requests() == []
