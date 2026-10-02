from __future__ import annotations

import inspect
import json
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.query_groups import InfrahubGroupContext, InfrahubGroupContextBase, InfrahubGroupContextSync
from infrahub_sdk.schema import NodeSchemaAPI, RelationshipCardinality, RelationshipKind, RelationshipSchemaAPI

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

async_methods = [method for method in dir(InfrahubGroupContext) if not method.startswith("_")]
sync_methods = [method for method in dir(InfrahubGroupContextSync) if not method.startswith("_")]

client_types = ["standard", "sync"]


async def test_method_sanity() -> None:
    """Validate that there is at least one public method and that both clients look the same."""
    assert async_methods
    assert async_methods == sync_methods


@pytest.mark.parametrize("method", async_methods)
async def test_validate_method_signature(
    method: str,
    replace_sync_return_annotation: Callable[[str], str],
    replace_async_return_annotation: Callable[[str], str],
) -> None:
    async_method = getattr(InfrahubGroupContext, method)
    sync_method = getattr(InfrahubGroupContextSync, method)
    async_sig = inspect.signature(async_method)
    sync_sig = inspect.signature(sync_method)
    assert async_sig.parameters == sync_sig.parameters
    assert async_sig.return_annotation == replace_sync_return_annotation(sync_sig.return_annotation)
    assert replace_async_return_annotation(async_sig.return_annotation) == sync_sig.return_annotation


def test_set_properties() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert context.identifier == "MYID"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"}, delete_unused_nodes=True)
    assert context.identifier == "MYID"
    assert context.params == {"one": 1, "two": "two"}
    assert context.delete_unused_nodes is True


def test_get_params_as_str() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._get_params_as_str() == "one: 1, two: two"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert not context._get_params_as_str()


def test_generate_group_name() -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert context._generate_group_name() == "MYID"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_name() == "MYID-11aaec5206c3dca37cbbcaaabf121550"

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_name(suffix="xxx") == "MYID-xxx-11aaec5206c3dca37cbbcaaabf121550"


def test_generate_group_description(std_group_schema: NodeSchemaAPI) -> None:
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID")
    assert not context._generate_group_description(schema=std_group_schema)

    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": 1, "two": "two"})
    assert context._generate_group_description(schema=std_group_schema) == "one: 1, two: two"

    assert std_group_schema.attributes[1].name == "description"
    std_group_schema.attributes[1].max_length = 20
    context = InfrahubGroupContextBase()
    context.set_properties(identifier="MYID", params={"one": "xxxxxxxxxxx", "two": "yyyyyyyyyyy"})
    assert context._generate_group_description(schema=std_group_schema) == "one: xxxxxxxxxx..."


GROUP_ID = "0f6a1b2c-3d4e-4f5a-8b6c-7d8e9f0a1b2c"
DEVICE_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
CABLE_ID = "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e"

GET_GROUP_QUERY = """
query Get_CoreStandardGroup ($offset: Int!, $limit: Int!) {
    CoreStandardGroup(name__value: "MYID", offset: $offset, limit: $limit) {
        count
        edges {
            node {
                id
                display_label
                __typename
                members {
                    edges {
                        node {
                            id
                            hfid
                            display_label
                            __typename
                        }
                    }
                }
            }
        }
    }
}
"""


@pytest.fixture
async def group_clients(clients: BothClients, std_group_schema: NodeSchemaAPI) -> BothClients:
    members = RelationshipSchemaAPI(
        name="members",
        peer="CoreNode",
        kind=RelationshipKind.GENERIC,
        cardinality=RelationshipCardinality.MANY,
        optional=True,
        identifier="group_member",
    )
    group_schema = std_group_schema.model_copy(update={"relationships": [*std_group_schema.relationships, members]})
    cache_data = {"version": "1.0", "nodes": [group_schema.model_dump()]}
    clients.standard.schema.set_cache(cache_data)
    clients.sync.schema.set_cache(cache_data)
    return clients


@pytest.mark.parametrize("client_type", client_types)
async def test_get_group_requests_member_references_only(
    httpx_mock: HTTPXMock, group_clients: BothClients, client_type: str
) -> None:
    member_edges = [
        {"node": {"id": DEVICE_ID, "hfid": ["dev1"], "display_label": "dev1", "__typename": "TestDevice"}},
        {"node": {"id": CABLE_ID, "hfid": ["c1"], "display_label": "c1", "__typename": "TestCable"}},
    ]
    group_data = {"id": GROUP_ID, "display_label": "MYID", "__typename": "CoreStandardGroup"}
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={
            "data": {
                "CoreStandardGroup": {
                    "count": 1,
                    "edges": [{"node": {**group_data, "members": {"edges": member_edges}}}],
                }
            }
        },
    )

    if client_type == "standard":
        client = group_clients.standard
        context = InfrahubGroupContext(client=client)
        context.set_properties(identifier="MYID")
        group = await context.get_group(store_peers=True)
    else:
        client = group_clients.sync
        context = InfrahubGroupContextSync(client=client)
        context.set_properties(identifier="MYID")
        group = context.get_group(store_peers=True)

    [request] = httpx_mock.get_requests()
    assert json.loads(request.content)["query"] == GET_GROUP_QUERY
    assert group is not None
    assert group.id == GROUP_ID
    assert group._get_relationship_many(name="members").peer_ids == [DEVICE_ID, CABLE_ID]
    assert context.previous_members is not None
    assert [(member.id, member.typename) for member in context.previous_members] == [
        (DEVICE_ID, "TestDevice"),
        (CABLE_ID, "TestCable"),
    ]
    assert client.store.get(key=DEVICE_ID, raise_when_missing=False) is None
    assert client.store.get(key=CABLE_ID, raise_when_missing=False) is None
