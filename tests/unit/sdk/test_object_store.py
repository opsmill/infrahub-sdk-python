import inspect

import httpx
import pytest
from pytest_httpx import HTTPXMock

from infrahub_sdk.exceptions import AuthenticationError
from infrahub_sdk.object_store import ObjectStore, ObjectStoreSync
from tests.unit.sdk.conftest import BothClients

async_methods = [method for method in dir(ObjectStore) if not method.startswith("_")]
sync_methods = [method for method in dir(ObjectStoreSync) if not method.startswith("_")]

client_types = ["standard", "sync"]

FILE_CONTENT_01 = """
    any content
    another content
    """


@pytest.fixture
async def mock_get_object_store_01(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.add_response(
        method="GET",
        text=FILE_CONTENT_01,
        match_headers={"X-Infrahub-Tracker": "object-store-get"},
    )
    return httpx_mock


@pytest.fixture
async def mock_upload_object_store_01(httpx_mock: HTTPXMock) -> HTTPXMock:
    payload = {"identifier": "xxxxxxxxxx", "checksum": "yyyyyyyyyyyyyy"}
    httpx_mock.add_response(
        method="POST",
        json=payload,
        match_headers={"X-Infrahub-Tracker": "object-store-upload"},
    )
    return httpx_mock


async def test_method_sanity() -> None:
    """Validate that there is at least one public method and that both clients look the same."""
    assert async_methods
    assert async_methods == sync_methods


@pytest.mark.parametrize("method", async_methods)
async def test_validate_method_signature(method: str) -> None:
    async_method = getattr(ObjectStore, method)
    sync_method = getattr(ObjectStoreSync, method)
    async_sig = inspect.signature(async_method)
    sync_sig = inspect.signature(sync_method)
    assert async_sig.parameters == sync_sig.parameters
    assert async_sig.return_annotation == sync_sig.return_annotation


@pytest.mark.parametrize("client_type", client_types)
async def test_object_store_get(client_type: str, clients: BothClients, mock_get_object_store_01: HTTPXMock) -> None:
    client = getattr(clients, client_type)

    if client_type == "standard":
        content = await client.object_store.get(identifier="aaaaaaaaa", tracker="object-store-get")
    else:
        content = client.object_store.get(identifier="aaaaaaaaa", tracker="object-store-get")

    assert content == FILE_CONTENT_01


@pytest.mark.parametrize("client_type", client_types)
async def test_object_store_upload(
    client_type: str, clients: BothClients, mock_upload_object_store_01: HTTPXMock
) -> None:
    client = getattr(clients, client_type)

    if client_type == "standard":
        response = await client.object_store.upload(content=FILE_CONTENT_01, tracker="object-store-upload")
    else:
        response = client.object_store.upload(content=FILE_CONTENT_01, tracker="object-store-upload")

    assert response == {"checksum": "yyyyyyyyyyyyyy", "identifier": "xxxxxxxxxx"}


@pytest.mark.parametrize("client_type", client_types)
async def test_object_store_get_raises_on_404(client_type: str, clients: BothClients, httpx_mock: HTTPXMock) -> None:
    """get() must raise on 404 — otherwise the response body is silently returned as 'content'."""
    httpx_mock.add_response(
        method="GET",
        status_code=404,
        json={"data": None, "errors": [{"message": "Unable to find the node ...", "extensions": {"code": 404}}]},
    )
    client = getattr(clients, client_type)

    with pytest.raises(httpx.HTTPStatusError) as exc:
        if client_type == "standard":
            await client.object_store.get(identifier="nonexistent")
        else:
            client.object_store.get(identifier="nonexistent")
    assert exc.value.response.status_code == 404


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("status_code", [401, 403])
async def test_object_store_get_raises_authentication_error(
    client_type: str, status_code: int, clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """get() must still convert 401/403 responses to AuthenticationError (unchanged behaviour)."""
    httpx_mock.add_response(
        method="GET",
        status_code=status_code,
        json={"errors": [{"message": "forbidden"}]},
    )
    client = getattr(clients, client_type)

    with pytest.raises(AuthenticationError):
        if client_type == "standard":
            await client.object_store.get(identifier="whatever")
        else:
            client.object_store.get(identifier="whatever")


@pytest.mark.parametrize("client_type", client_types)
async def test_object_store_upload_raises_on_500(client_type: str, clients: BothClients, httpx_mock: HTTPXMock) -> None:
    """upload() must raise on server errors — otherwise resp.json() returns the error payload as if it were a successful upload."""
    httpx_mock.add_response(
        method="POST",
        status_code=500,
        json={"data": None, "errors": [{"message": "internal server error", "extensions": {"code": 500}}]},
    )
    client = getattr(clients, client_type)

    with pytest.raises(httpx.HTTPStatusError) as exc:
        if client_type == "standard":
            await client.object_store.upload(content="irrelevant")
        else:
            client.object_store.upload(content="irrelevant")
    assert exc.value.response.status_code == 500
