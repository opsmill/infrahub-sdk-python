from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from infrahub_sdk import Config, InfrahubClient, InfrahubClientSync, Priority
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from tests.unit.sdk.conftest import BothClients

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

client_types = ["standard", "sync"]


def _build_clients(priority: Priority) -> BothClients:
    return BothClients(
        standard=InfrahubClient(
            config=Config(address="http://mock", insert_tracker=True, pagination_size=3, priority=priority)
        ),
        sync=InfrahubClientSync(
            config=Config(address="http://mock", insert_tracker=True, pagination_size=3, priority=priority)
        ),
    )


@pytest.fixture
def low_clients() -> BothClients:
    return _build_clients(Priority.LOW)


@pytest.fixture
def normal_clients() -> BothClients:
    return _build_clients(Priority.NORMAL)


@pytest.mark.parametrize("client_type", client_types)
async def test_priority_header_on_graphql_query(
    client_type: str, low_clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """A client with a default priority emits X-Priority on a GraphQL query."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
        match_headers={"X-Priority": "low"},
    )

    query = "query { InfrahubInfo { version }}"
    client = getattr(low_clients, client_type)
    if client_type == "standard":
        await client.execute_graphql(query=query)
    else:
        client.execute_graphql(query=query)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "low"


@pytest.mark.parametrize("client_type", client_types)
async def test_priority_header_on_graphql_mutation(
    client_type: str, low_clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """A client with a default priority emits X-Priority on a GraphQL mutation."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinTagCreate": {"ok": True, "object": {"id": "tag-1"}}}},
        match_headers={"X-Priority": "low"},
    )

    mutation = 'mutation { BuiltinTagCreate(data: {name: {value: "blue"}}) { ok } }'
    client = getattr(low_clients, client_type)
    if client_type == "standard":
        await client.execute_graphql(query=mutation)
    else:
        client.execute_graphql(query=mutation)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "low"


@pytest.mark.parametrize("client_type", client_types)
async def test_priority_header_on_blob_download(
    client_type: str, low_clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """A client with a default priority emits X-Priority on an object-store blob download."""
    httpx_mock.add_response(
        method="GET",
        text="any content",
        match_headers={"X-Priority": "low"},
    )

    client = getattr(low_clients, client_type)
    if client_type == "standard":
        content = await client.object_store.get(identifier="aaaaaaaaa")
    else:
        content = client.object_store.get(identifier="aaaaaaaaa")

    assert content == "any content"
    requests = [r for r in httpx_mock.get_requests() if r.method == "GET"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "low"


@pytest.mark.parametrize("client_type", client_types)
async def test_priority_header_on_blob_upload(
    client_type: str, low_clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """A client with a default priority emits X-Priority on an object-store blob upload."""
    httpx_mock.add_response(
        method="POST",
        json={"identifier": "xxxxxxxxxx", "checksum": "yyyyyyyyyyyyyy"},
        match_headers={"X-Priority": "low"},
    )

    client = getattr(low_clients, client_type)
    if client_type == "standard":
        response = await client.object_store.upload(content="any content")
    else:
        response = client.object_store.upload(content="any content")

    assert response == {"checksum": "yyyyyyyyyyyyyy", "identifier": "xxxxxxxxxx"}
    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "low"


@pytest.mark.parametrize("client_type", client_types)
async def test_priority_header_on_multipart_upload(
    client_type: str,
    low_clients: BothClients,
    file_object_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    """A client with a default priority emits X-Priority on a multipart file upload.

    Confirms the header survives the ``content-type`` pop performed for multipart requests.
    """
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "NetworkCircuitContractCreate": {
                    "ok": True,
                    "object": {
                        "id": "new-file-node-123",
                        "display_label": "contract.pdf",
                        "file_name": {"value": "contract.pdf"},
                        "checksum": {"value": "abc123checksum"},
                        "file_size": {"value": 17},
                        "file_type": {"value": "application/pdf"},
                        "storage_id": {"value": "storage-xyz-789"},
                        "contract_start": {"value": "2024-01-01T00:00:00Z"},
                        "contract_end": {"value": "2024-12-31T23:59:59Z"},
                    },
                }
            }
        },
        match_headers={"X-Priority": "low"},
    )

    client = getattr(low_clients, client_type)
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.contract_start.value = "2024-01-01T00:00:00Z"  # type: ignore[union-attr]
    node.contract_end.value = "2024-12-31T23:59:59Z"  # type: ignore[union-attr]
    node.upload_from_bytes(content=b"Test file content", name="contract.pdf")

    if isinstance(node, InfrahubNode):
        await node.save()
    else:
        node.save()

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "low"
    assert requests[0].headers.get("content-type").startswith("multipart/form-data;")


@pytest.mark.parametrize("client_type", client_types)
async def test_priority_header_on_batched_requests(
    client_type: str, low_clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """Every request issued through a batch carries the client-wide X-Priority header."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
        match_headers={"X-Priority": "low"},
        is_reusable=True,
    )

    query = "query { InfrahubInfo { version }}"
    tasks_number = 3
    client = getattr(low_clients, client_type)

    if client_type == "standard":
        batch = await client.create_batch()
        for _ in range(tasks_number):
            batch.add(task=client.execute_graphql, query=query)
        async for _, _result in batch.execute():
            pass
    else:
        batch = client.create_batch()
        for _ in range(tasks_number):
            batch.add(task=client.execute_graphql, query=query)
        for _, _result in batch.execute():
            pass

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == tasks_number
    assert all(r.headers["x-priority"] == "low" for r in requests)


@pytest.mark.parametrize("client_type", client_types)
async def test_priority_normal_is_always_emitted(
    client_type: str, normal_clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """An explicitly configured default (normal) is always emitted, never omitted."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
        match_headers={"X-Priority": "normal"},
    )

    query = "query { InfrahubInfo { version }}"
    client = getattr(normal_clients, client_type)
    if client_type == "standard":
        await client.execute_graphql(query=query)
    else:
        client.execute_graphql(query=query)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "normal"
