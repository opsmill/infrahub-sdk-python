from __future__ import annotations

from datetime import datetime, timezone
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


@pytest.mark.parametrize("client_type", client_types)
async def test_no_priority_header_on_graphql_when_unconfigured(
    client_type: str, clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """An unconfigured client emits no X-Priority header on a GraphQL request."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
    )

    query = "query { InfrahubInfo { version }}"
    client = getattr(clients, client_type)
    if client_type == "standard":
        await client.execute_graphql(query=query)
    else:
        client.execute_graphql(query=query)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert "x-priority" not in requests[0].headers


@pytest.mark.parametrize("client_type", client_types)
async def test_no_priority_header_on_blob_download_when_unconfigured(
    client_type: str, clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """An unconfigured client emits no X-Priority header on an object-store blob download."""
    httpx_mock.add_response(
        method="GET",
        text="any content",
    )

    client = getattr(clients, client_type)
    if client_type == "standard":
        content = await client.object_store.get(identifier="aaaaaaaaa")
    else:
        content = client.object_store.get(identifier="aaaaaaaaa")

    assert content == "any content"
    requests = [r for r in httpx_mock.get_requests() if r.method == "GET"]
    assert len(requests) == 1
    assert "x-priority" not in requests[0].headers


@pytest.mark.parametrize("client_type", client_types)
async def test_no_priority_header_on_blob_upload_when_unconfigured(
    client_type: str, clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """An unconfigured client emits no X-Priority header on an object-store blob upload."""
    httpx_mock.add_response(
        method="POST",
        json={"identifier": "xxxxxxxxxx", "checksum": "yyyyyyyyyyyyyy"},
    )

    client = getattr(clients, client_type)
    if client_type == "standard":
        response = await client.object_store.upload(content="any content")
    else:
        response = client.object_store.upload(content="any content")

    assert response == {"checksum": "yyyyyyyyyyyyyy", "identifier": "xxxxxxxxxx"}
    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert "x-priority" not in requests[0].headers


@pytest.mark.parametrize("client_type", client_types)
async def test_no_priority_header_on_multipart_upload_when_unconfigured(
    client_type: str,
    clients: BothClients,
    file_object_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    """An unconfigured client emits no X-Priority header on a multipart file upload."""
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
    )

    client = getattr(clients, client_type)
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
    assert "x-priority" not in requests[0].headers
    assert requests[0].headers.get("content-type").startswith("multipart/form-data;")


@pytest.mark.parametrize("client_type", client_types)
async def test_unconfigured_headers_unchanged_versus_baseline(
    client_type: str, clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """With no priority and no per-request arg, the SDK-set outgoing headers are unchanged.

    Only the absence of X-Priority matters; the request still carries the baseline SDK
    headers it always had (``content-type`` and, since ``insert_tracker`` is set, the
    ``X-Infrahub-Tracker`` header). Transport-injected headers (host, user-agent, etc.)
    are intentionally not asserted.
    """
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
    )

    query = "query { InfrahubInfo { version }}"
    tracker = "test-priority-baseline"
    client = getattr(clients, client_type)
    if client_type == "standard":
        await client.execute_graphql(query=query, tracker=tracker)
    else:
        client.execute_graphql(query=query, tracker=tracker)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    request = requests[0]
    assert "x-priority" not in request.headers
    assert request.headers["content-type"].startswith("application/json")
    assert request.headers["x-infrahub-tracker"] == tracker


# ---------------------------------------------------------------------------
# User Story 2: per-request override
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("client_type", client_types)
async def test_override_on_no_default_client_then_no_leak(
    client_type: str, clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """On a no-default client, priority=HIGH emits the header; the next un-annotated call emits none."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
        is_reusable=True,
    )

    query = "query { InfrahubInfo { version }}"
    client = getattr(clients, client_type)
    if client_type == "standard":
        await client.execute_graphql(query=query, priority=Priority.HIGH)
        await client.execute_graphql(query=query)
    else:
        client.execute_graphql(query=query, priority=Priority.HIGH)
        client.execute_graphql(query=query)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 2
    assert requests[0].headers["x-priority"] == "high"
    assert "x-priority" not in requests[1].headers


@pytest.mark.parametrize("client_type", client_types)
async def test_override_beats_default_then_reverts(
    client_type: str, low_clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """A per-request HIGH overrides a LOW default for one call; the next call reverts to LOW."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
        is_reusable=True,
    )

    query = "query { InfrahubInfo { version }}"
    client = getattr(low_clients, client_type)
    if client_type == "standard":
        await client.execute_graphql(query=query, priority=Priority.HIGH)
        await client.execute_graphql(query=query)
    else:
        client.execute_graphql(query=query, priority=Priority.HIGH)
        client.execute_graphql(query=query)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 2
    assert requests[0].headers["x-priority"] == "high"
    assert requests[1].headers["x-priority"] == "low"


@pytest.mark.parametrize("client_type", client_types)
async def test_override_normal_beats_low_default(
    client_type: str, low_clients: BothClients, httpx_mock: HTTPXMock
) -> None:
    """An explicit per-request NORMAL steps up over a LOW default (explicit value always wins)."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"InfrahubInfo": {"version": "1.0"}}},
        match_headers={"X-Priority": "normal"},
    )

    query = "query { InfrahubInfo { version }}"
    client = getattr(low_clients, client_type)
    if client_type == "standard":
        await client.execute_graphql(query=query, priority=Priority.NORMAL)
    else:
        client.execute_graphql(query=query, priority=Priority.NORMAL)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "normal"


@pytest.mark.parametrize("client_type", client_types)
async def test_override_on_get(
    client_type: str, clients: BothClients, mock_schema_query_01: HTTPXMock, httpx_mock: HTTPXMock
) -> None:
    """A per-request priority on get() reaches the underlying GraphQL request."""
    response = {
        "data": {
            "CoreRepository": {
                "edges": [
                    {
                        "node": {
                            "__typename": "CoreRepository",
                            "id": "bfae43e8-5ebb-456c-a946-bf64e930710a",
                            "name": {"value": "infrahub-demo-core"},
                            "location": {"value": "git@github.com:opsmill/infrahub-demo-core.git"},
                            "commit": {"value": "bbbbbbbbbbbbbbbbbbbb"},
                        }
                    }
                ]
            }
        }
    }
    httpx_mock.add_response(
        method="POST",
        json=response,
        match_headers={"X-Priority": "high"},
        is_reusable=True,
    )

    node_id = "bfae43e8-5ebb-456c-a946-bf64e930710a"
    client = getattr(clients, client_type)
    if client_type == "standard":
        await client.get(kind="CoreRepository", id=node_id, priority=Priority.HIGH)
    else:
        client.get(kind="CoreRepository", id=node_id, priority=Priority.HIGH)

    query_requests = [
        r
        for r in httpx_mock.get_requests()
        if r.method == "POST" and r.headers.get("x-infrahub-tracker") == "query-corerepository-page1"
    ]
    assert len(query_requests) == 1
    assert query_requests[0].headers["x-priority"] == "high"


@pytest.mark.parametrize("client_type", client_types)
async def test_override_on_all_carries_on_every_page(
    client_type: str,
    clients: BothClients,
    mock_query_repository_page1_2: HTTPXMock,
    mock_query_repository_page2_2: HTTPXMock,
    httpx_mock: HTTPXMock,
) -> None:
    """The override is forwarded on every page request of a paginated all()."""
    client = getattr(clients, client_type)
    if client_type == "standard":
        repos = await client.all(kind="CoreRepository", priority=Priority.HIGH)
    else:
        repos = client.all(kind="CoreRepository", priority=Priority.HIGH)
    assert len(repos) == 5

    page_requests = [
        r
        for r in httpx_mock.get_requests()
        if r.method == "POST" and (r.headers.get("x-infrahub-tracker") or "").startswith("query-corerepository-page")
    ]
    assert len(page_requests) == 2
    assert all(r.headers["x-priority"] == "high" for r in page_requests)


@pytest.mark.parametrize("client_type", client_types)
async def test_override_on_save_create_path(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI, httpx_mock: HTTPXMock
) -> None:
    """A per-request priority on node.save() reaches the create mutation."""
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {"BuiltinLocationCreate": {"ok": True, "object": {"id": "17aec828-9814-ce00-3f20-1a053670f1c8"}}}
        },
        is_reusable=True,
    )

    client = getattr(clients, client_type)
    data = {"name": {"value": "JFK1"}, "type": {"value": "SITE"}}
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=location_schema, data=data)
        await node.save(priority=Priority.HIGH)
    else:
        node = InfrahubNodeSync(client=client, schema=location_schema, data=data)
        node.save(priority=Priority.HIGH)

    create_requests = [
        r
        for r in httpx_mock.get_requests()
        if r.method == "POST" and r.headers.get("x-infrahub-tracker") == "mutation-builtinlocation-create"
    ]
    assert len(create_requests) == 1
    assert create_requests[0].headers["x-priority"] == "high"


@pytest.mark.parametrize("client_type", client_types)
async def test_override_on_diff_method(client_type: str, clients: BothClients, httpx_mock: HTTPXMock) -> None:
    """A per-request priority on a diff method reaches the GraphQL request."""
    httpx_mock.add_response(
        method="POST",
        json={"data": {"DiffUpdate": {"ok": True}}},
        match_headers={"X-Priority": "high"},
    )

    from_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    to_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
    client = getattr(clients, client_type)
    if client_type == "standard":
        await client.create_diff(
            branch="main", name="test-diff", from_time=from_time, to_time=to_time, priority=Priority.HIGH
        )
    else:
        client.create_diff(
            branch="main", name="test-diff", from_time=from_time, to_time=to_time, priority=Priority.HIGH
        )

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "high"


@pytest.mark.parametrize("client_type", client_types)
async def test_override_on_multipart_upload(
    client_type: str,
    clients: BothClients,
    file_object_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    """A per-request priority survives the multipart content-type pop on a file upload."""
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
        match_headers={"X-Priority": "high"},
    )

    client = getattr(clients, client_type)
    if client_type == "standard":
        node = InfrahubNode(client=client, schema=file_object_schema, branch="main")
    else:
        node = InfrahubNodeSync(client=client, schema=file_object_schema, branch="main")

    node.contract_start.value = "2024-01-01T00:00:00Z"  # type: ignore[union-attr]
    node.contract_end.value = "2024-12-31T23:59:59Z"  # type: ignore[union-attr]
    node.upload_from_bytes(content=b"Test file content", name="contract.pdf")

    if isinstance(node, InfrahubNode):
        await node.save(priority=Priority.HIGH)
    else:
        node.save(priority=Priority.HIGH)

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(requests) == 1
    assert requests[0].headers["x-priority"] == "high"
    assert requests[0].headers.get("content-type").startswith("multipart/form-data;")
