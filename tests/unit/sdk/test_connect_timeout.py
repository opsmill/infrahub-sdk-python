"""Connect-phase timeout handling on the async and sync clients.

Covers the split connect/request timeout handed to httpx, the cap of the connect timeout by the
per-request timeout, and the conversion of ``httpx.ConnectTimeout`` into ``ServerNotReachableError``
on every request path so that ``retry_on_failure`` retries it like any other connection failure.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import ValidationError

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync
from infrahub_sdk.exceptions import ServerNotReachableError
from infrahub_sdk.types import HTTPMethod

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

CLIENT_TYPES = ["standard", "sync"]

# ``_request_multipart`` and ``_get_streaming`` build their own httpx client, so each path is driven
# separately to prove they all share the same timeout and error handling.
REQUEST_PATHS = ["regular", "multipart", "streaming"]

URL = "http://mock/graphql/main"


def _make_client(
    client_type: str, *, connect_timeout: int = 10, retry_on_failure: bool = False, retry_delay: int = 5
) -> InfrahubClient | InfrahubClientSync:
    """Build a client with no ``requester`` override so the real (mocked) httpx transport is used."""
    cfg = Config(
        address="http://mock",
        connect_timeout=connect_timeout,
        retry_on_failure=retry_on_failure,
        retry_delay=retry_delay,
    )
    if client_type == "standard":
        return InfrahubClient(config=cfg)
    return InfrahubClientSync(config=cfg)


async def _drive_path(client: InfrahubClient | InfrahubClientSync, path: str, timeout: int) -> httpx.Response:
    """Send one request on the selected path and return the (fully read) response."""
    if path == "regular":
        if isinstance(client, InfrahubClient):
            return await client._request(url=URL, method=HTTPMethod.POST, headers={}, timeout=timeout, payload={})
        return client._request(url=URL, method=HTTPMethod.POST, headers={}, timeout=timeout, payload={})

    if path == "multipart":
        files = {"file": ("upload.bin", io.BytesIO(b"file body"), "application/octet-stream")}
        if isinstance(client, InfrahubClient):
            return await client._request_multipart(url=URL, headers={}, timeout=timeout, files=files)
        return client._request_multipart(url=URL, headers={}, timeout=timeout, files=files)

    if isinstance(client, InfrahubClient):
        async with client._get_streaming(url=URL, timeout=timeout) as response:
            await response.aread()
            return response
    with client._get_streaming(url=URL, timeout=timeout) as response:
        response.read()
        return response


# --- Configuration ------------------------------------------------------------------------------


def test_default_connect_timeout_is_shorter_than_request_timeout() -> None:
    config = Config(address="http://mock")

    assert config.connect_timeout == 10
    assert config.connect_timeout < config.timeout


def test_connect_timeout_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFRAHUB_CONNECT_TIMEOUT", "3")

    assert Config(address="http://mock").connect_timeout == 3


def test_connect_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Config(address="http://mock", connect_timeout=0)


# --- Timeout handed to httpx -------------------------------------------------------------------


@pytest.mark.parametrize("path", REQUEST_PATHS)
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_request_uses_connect_timeout_for_connect_phase_only(
    client_type: str, path: str, httpx_mock: HTTPXMock
) -> None:
    """Every request path bounds the connect phase with ``connect_timeout`` and the rest with ``timeout``."""
    httpx_mock.add_response(status_code=200, json={"data": {}})
    client = _make_client(client_type, connect_timeout=4)

    await _drive_path(client=client, path=path, timeout=30)

    request = httpx_mock.get_request()
    assert request is not None
    assert request.extensions["timeout"] == {"connect": 4.0, "read": 30.0, "write": 30.0, "pool": 30.0}


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_connect_timeout_is_capped_by_request_timeout(client_type: str, httpx_mock: HTTPXMock) -> None:
    """A per-request ``timeout`` shorter than ``connect_timeout`` also bounds the connect phase."""
    httpx_mock.add_response(status_code=200, json={"data": {}})
    client = _make_client(client_type, connect_timeout=10)

    await _drive_path(client=client, path="regular", timeout=3)

    request = httpx_mock.get_request()
    assert request is not None
    assert request.extensions["timeout"]["connect"] == pytest.approx(3.0)


# --- ConnectTimeout is a connection failure -----------------------------------------------------


@pytest.mark.parametrize("path", REQUEST_PATHS)
@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_connect_timeout_raises_server_not_reachable(client_type: str, path: str, httpx_mock: HTTPXMock) -> None:
    """``httpx.ConnectTimeout`` surfaces as ``ServerNotReachableError`` on every request path."""
    httpx_mock.add_exception(httpx.ConnectTimeout("timed out"))
    client = _make_client(client_type)

    with pytest.raises(ServerNotReachableError) as excinfo:
        await _drive_path(client=client, path=path, timeout=10)

    assert isinstance(excinfo.value.__cause__, httpx.ConnectTimeout)
    assert excinfo.value.address == "http://mock"


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_execute_graphql_retries_after_connect_timeout(client_type: str, httpx_mock: HTTPXMock) -> None:
    """With ``retry_on_failure`` enabled, a connect timeout is retried and the next attempt succeeds."""
    httpx_mock.add_exception(httpx.ConnectTimeout("timed out"))
    httpx_mock.add_response(status_code=200, json={"data": {"ok": True}})
    client = _make_client(client_type, retry_on_failure=True, retry_delay=0)

    if isinstance(client, InfrahubClient):
        data = await client.execute_graphql(query="query { ok }")
    else:
        data = client.execute_graphql(query="query { ok }")

    assert data == {"ok": True}
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
async def test_execute_graphql_surfaces_connect_timeout_without_retry(client_type: str, httpx_mock: HTTPXMock) -> None:
    """Without ``retry_on_failure``, a connect timeout is raised once as ``ServerNotReachableError``."""
    httpx_mock.add_exception(httpx.ConnectTimeout("timed out"))
    client = _make_client(client_type)

    with pytest.raises(ServerNotReachableError):
        if isinstance(client, InfrahubClient):
            await client.execute_graphql(query="query { ok }")
        else:
            client.execute_graphql(query="query { ok }")

    assert len(httpx_mock.get_requests()) == 1
