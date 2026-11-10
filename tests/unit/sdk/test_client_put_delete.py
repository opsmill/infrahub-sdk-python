from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

URL = "http://mock/api/example"
client_types = ["standard", "sync"]


def _build_password_client(client_type: str) -> InfrahubClient | InfrahubClientSync:
    config = Config(address="http://mock", username="admin", password="password")
    client: InfrahubClient | InfrahubClientSync = (
        InfrahubClient(config=config) if client_type == "standard" else InfrahubClientSync(config=config)
    )
    client.access_token = "OLD"
    client.refresh_token = "refresh-token"
    client.headers["Authorization"] = "Bearer OLD"
    return client


async def _put(client: InfrahubClient | InfrahubClientSync, payload: dict) -> None:
    if isinstance(client, InfrahubClient):
        await client._put(url=URL, payload=payload)
    else:
        client._put(url=URL, payload=payload)


async def _delete(client: InfrahubClient | InfrahubClientSync) -> None:
    if isinstance(client, InfrahubClient):
        await client._delete(url=URL)
    else:
        client._delete(url=URL)


@pytest.mark.parametrize("client_type", client_types)
async def test_put_sends_the_payload_as_json(client_type: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=URL, json={})

    await _put(_build_password_client(client_type), payload={"ratio": 0.5})

    request = httpx_mock.get_request()
    assert request is not None
    assert json.loads(request.content) == {"ratio": 0.5}
    assert request.headers["Authorization"] == "Bearer OLD"


@pytest.mark.parametrize("client_type", client_types)
async def test_delete_sends_no_body(client_type: str, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="DELETE", url=URL, json={})

    await _delete(_build_password_client(client_type))

    request = httpx_mock.get_request()
    assert request is not None
    assert request.content == b""
    assert request.headers["Authorization"] == "Bearer OLD"


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("client_type", client_types)
async def test_expired_token_is_refreshed_and_the_request_retried(
    client_type: str, method: str, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method=method, url=URL, status_code=401, json={"errors": [{"message": "Expired Signature"}]}
    )
    httpx_mock.add_response(method="POST", url="http://mock/api/auth/refresh", json={"access_token": "NEW"})
    httpx_mock.add_response(method=method, url=URL, json={})

    client = _build_password_client(client_type)
    if method == "PUT":
        await _put(client, payload={"ratio": 0.5})
    else:
        await _delete(client)

    requests = [request for request in httpx_mock.get_requests() if str(request.url) == URL]
    assert [request.headers["Authorization"] for request in requests] == ["Bearer OLD", "Bearer NEW"]
