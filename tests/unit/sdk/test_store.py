from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import NodeInvalidError, NodeNotFoundError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.node.attribute import Attribute
from infrahub_sdk.protocols import BuiltinIPAddressSync, BuiltinIPPrefix
from infrahub_sdk.schema import NodeSchema
from infrahub_sdk.store import NodeStore, NodeStoreSync, get_schema_name
from infrahub_sdk.transforms import InfrahubTransform

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI

    from .conftest import BothClients

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set(client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    node = node_class(client=client, schema=schema_with_hfid["location"], data=data)

    store.set(key="mykey", node=node)

    assert node._internal_id in store._branches[client.default_branch]._objs
    assert "mykey" in store._branches[client.default_branch]._keys
    assert store._branches[client.default_branch]._keys["mykey"] == node._internal_id


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set_no_hfid(client_type: str, clients: BothClients, location_schema: NodeSchemaAPI) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    node = node_class(client=client, schema=location_schema, data=data)

    store.set(key="mykey", node=node)

    assert store._branches[client.default_branch]._objs[node._internal_id] == node
    assert node._internal_id in store._branches[client.default_branch]._objs
    assert "mykey" in store._branches[client.default_branch]._keys
    assert store._branches[client.default_branch]._keys["mykey"] == node._internal_id

    branch_name = "mybranch"
    store.set(key="anotherkey", node=node, branch=branch_name)

    assert store._branches[branch_name]._objs[node._internal_id] == node
    assert node._internal_id in store._branches[branch_name]._objs
    assert "anotherkey" in store._branches[branch_name]._keys
    assert store._branches[branch_name]._keys["anotherkey"] == node._internal_id


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_get(client_type: str, clients: BothClients, location_schema: NodeSchemaAPI) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    data = {
        "id": "54f3108c-1f21-44c4-93cf-ec5737587b48",
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    node = node_class(client=client, schema=location_schema, data=data)

    store.set(key="mykey", node=node)

    assert store.get(key=node._internal_id).id == node.id
    assert store.get(kind="BuiltinLocation", key="mykey").id == node.id
    assert store.get(key="mykey").id == node.id

    assert store.get(kind="BuiltinTest", key="mykey", raise_when_missing=False) is None

    assert store.get(kind="BuiltinLocation", key="anotherkey", raise_when_missing=False) is None
    assert store.get(key="anotherkey", raise_when_missing=False) is None

    with pytest.raises(NodeNotFoundError):
        store.get(kind="BuiltinLocation", key="anotherkey")
    with pytest.raises(NodeNotFoundError):
        store.get(key="anotherkey")
    with pytest.raises(NodeNotFoundError):
        store.get(key="mykey", branch="mybranch")

    with pytest.raises(NodeInvalidError):
        store.get(kind="BuiltinTest", key="mykey")

    store.set(key="mykey", node=node, branch="mybranch")
    assert store.get(key="mykey", branch="mybranch").id == node.id


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_get_with_hfid(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    data = {
        "id": "54f3108c-1f21-44c4-93cf-ec5737587b48",
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    node = node_class(client=client, schema=schema_with_hfid["location"], data=data)

    store.set(key="mykey", node=node)

    assert store.get(key=node._internal_id).id == node.id

    assert store.get(kind="BuiltinLocation", key="mykey").id == node.id
    assert store.get(key="mykey").id == node.id
    assert store.get(key="BuiltinLocation__JFK1").id == node.id
    assert store.get(kind="BuiltinLocation", key="JFK1").id == node.id
    assert store.get(key="54f3108c-1f21-44c4-93cf-ec5737587b48").id == node.id

    assert store.get(kind="BuiltinLocation", key="anotherkey", raise_when_missing=False) is None
    assert store.get(key="anotherkey", raise_when_missing=False) is None

    with pytest.raises(NodeNotFoundError):
        store.get(kind="BuiltinLocation", key="anotherkey")
    with pytest.raises(NodeNotFoundError):
        store.get(key="anotherkey")


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set_same_id_replaces_previous_copy(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    node_id = "54f3108c-1f21-44c4-93cf-ec5737587b48"
    first = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": node_id, "name": {"value": "JFK1"}, "type": {"value": "SITE"}},
    )
    second = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": node_id, "name": {"value": "JFK2"}, "type": {"value": "SITE"}},
    )

    store.set(key="mykey", node=first)
    store.set(node=second)

    assert store.count() == 1
    assert store.get(key=node_id) is second
    assert store.get(key="mykey") is second
    assert store.get(key="BuiltinLocation__JFK2") is second
    assert store.get(key="BuiltinLocation__JFK1", raise_when_missing=False) is None
    assert store.get(key=first._internal_id, raise_when_missing=False) is None


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set_same_id_without_hfid_keeps_previous_hfid(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    node_id = "54f3108c-1f21-44c4-93cf-ec5737587b48"
    first = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": node_id, "name": {"value": "JFK1"}, "type": {"value": "SITE"}},
    )
    second = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": node_id, "type": {"value": "SITE"}},
    )
    assert second.get_human_friendly_id() is None

    store.set(node=first)
    store.set(node=second)

    assert store.count() == 1
    assert store.get(key="BuiltinLocation__JFK1") is second
    assert store.get(kind="BuiltinLocation", key="JFK1") is second


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set_same_id_twice_without_hfid_keeps_previous_hfid(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    node_id = "54f3108c-1f21-44c4-93cf-ec5737587b48"
    first = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": node_id, "name": {"value": "JFK1"}, "type": {"value": "SITE"}},
    )
    second = node_class(client=client, schema=schema_with_hfid["location"], data={"id": node_id})
    third = node_class(client=client, schema=schema_with_hfid["location"], data={"id": node_id})

    store.set(node=first)
    store.set(node=second)
    store.set(node=third)

    assert store.count() == 1
    assert store.get(key="BuiltinLocation__JFK1") is third


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set_same_id_after_local_rename_removes_every_previous_hfid(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    node_id = "54f3108c-1f21-44c4-93cf-ec5737587b48"
    first = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": node_id, "name": {"value": "JFK1"}, "type": {"value": "SITE"}},
    )
    store.set(node=first)
    name = first.name
    assert isinstance(name, Attribute)
    name.value = "JFK2"
    store.set(node=first)
    second = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": node_id, "name": {"value": "JFK2"}, "type": {"value": "SITE"}},
    )
    store.set(node=second)

    assert store.count() == 1
    assert store.get(key="BuiltinLocation__JFK2") is second
    assert store.get(key="BuiltinLocation__JFK1", raise_when_missing=False) is None
    with pytest.raises(NodeNotFoundError, match=r"Unable to find the node 'BuiltinLocation__JFK1' in the store"):
        store.get(key="BuiltinLocation__JFK1")


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set_same_object_after_rename_removes_previous_hfid(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    node = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": "54f3108c-1f21-44c4-93cf-ec5737587b48", "name": {"value": "JFK1"}, "type": {"value": "SITE"}},
    )
    store.set(key="mykey", node=node)
    name = node.name
    assert isinstance(name, Attribute)
    name.value = "JFK2"
    store.set(node=node)

    assert store.count() == 1
    assert store.get(key="BuiltinLocation__JFK2") is node
    assert store.get(key="mykey") is node
    assert store.get(key="BuiltinLocation__JFK1", raise_when_missing=False) is None


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set_object_stored_before_it_had_an_id_removes_previous_hfid(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    node_id = "54f3108c-1f21-44c4-93cf-ec5737587b48"
    queried = node_class(
        client=client,
        schema=schema_with_hfid["location"],
        data={"id": node_id, "name": {"value": "JFK1"}, "type": {"value": "SITE"}},
    )
    store.set(node=queried)
    node = node_class(
        client=client, schema=schema_with_hfid["location"], data={"name": {"value": "JFK1"}, "type": {"value": "SITE"}}
    )
    store.set(key="mykey", node=node)
    name = node.name
    assert isinstance(name, Attribute)
    name.value = "JFK2"
    node.id = node_id
    store.set(node=node)

    assert store.count() == 1
    assert store.get(key=node_id) is node
    assert store.get(key="mykey") is node
    assert store.get(key="BuiltinLocation__JFK2") is node
    assert store.get(key="BuiltinLocation__JFK1", raise_when_missing=False) is None
    assert store.get(key=queried._internal_id, raise_when_missing=False) is None


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set_later_copy_replaces_stored_node(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    if client_type == "standard":
        client = clients.standard
        store = NodeStore(default_branch="main")
        node_class = InfrahubNode
    else:
        client = clients.sync
        store = NodeStoreSync(default_branch="main")
        node_class = InfrahubNodeSync

    node_id = "54f3108c-1f21-44c4-93cf-ec5737587b48"

    def build(name: str) -> InfrahubNode | InfrahubNodeSync:
        return node_class(
            client=client,
            schema=schema_with_hfid["location"],
            data={"id": node_id, "name": {"value": name}, "type": {"value": "SITE"}},
        )

    def stored_name() -> str | None:
        name = store.get(key=node_id).name
        assert isinstance(name, Attribute)
        return name.value

    store.set(node=build("JFK1"))
    store.set(node=build("JFK2"))
    store.set(node=build("JFK3"))

    assert store.count() == 1
    assert stored_name() == "JFK3"
    assert store.get(key="BuiltinLocation__JFK2", raise_when_missing=False) is None


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_get_unknown_branch_does_not_create_it(client_type: str) -> None:
    store = NodeStore(default_branch="main") if client_type == "standard" else NodeStoreSync(default_branch="main")

    assert store.get(key="mykey", branch="unknown", raise_when_missing=False) is None
    with pytest.raises(NodeNotFoundError, match=r"Unable to find the node 'mykey' in the store \(unknown\)"):
        store.get(key="mykey", branch="unknown")

    assert "unknown" not in store._branches


def test_store_get_schema_name() -> None:
    assert get_schema_name(schema=BuiltinIPPrefix) == BuiltinIPPrefix.__name__
    assert get_schema_name(schema=BuiltinIPAddressSync) == BuiltinIPAddressSync.__name__[:-4]


PERSON_ID = "33333333-3333-3333-3333-333333333333"
CAR_ID = "44444444-4444-4444-4444-444444444444"
TAG_ID = "11111111-1111-1111-1111-111111111111"
GROUP_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def person_with_cars_schema() -> dict[str, Any]:
    person = NodeSchema(
        name="Person",
        namespace="Testing",
        human_friendly_id=["name__value"],
        attributes=[
            {"name": "name", "kind": "Text", "unique": True},
            {"name": "age", "kind": "Number", "optional": True},
        ],
        relationships=[{"name": "cars", "peer": "TestingCar", "cardinality": "many", "optional": True}],
    ).convert_api()
    car = NodeSchema(
        name="Car",
        namespace="Testing",
        human_friendly_id=["name__value"],
        attributes=[{"name": "name", "kind": "Text", "unique": True}],
        relationships=[{"name": "owner", "peer": "TestingPerson", "cardinality": "one", "optional": True}],
    ).convert_api()
    return {"version": "1.0", "nodes": [person.model_dump(), car.model_dump()]}


class PersonFromStoreTransform(InfrahubTransform):
    query = "person_with_cars"

    async def transform(self, data: dict) -> dict:
        person = self.store.get(key="John", kind="TestingPerson")
        return {"name": person.name.value, "age": person.age.value}


async def test_transform_store_returns_main_node_by_hfid_when_its_peer_references_it_back(
    clients: BothClients, person_with_cars_schema: dict[str, Any]
) -> None:
    """In one response, the car's owner is an id-only copy of the person: it must not hide the person's values."""
    transform = PersonFromStoreTransform(
        client=clients.standard, infrahub_node=InfrahubNode, convert_query_response=True, branch="main"
    )
    transform.client.schema.set_cache(person_with_cars_schema, branch="main")
    data = {
        "TestingPerson": {
            "edges": [
                {
                    "node": {
                        "id": PERSON_ID,
                        "__typename": "TestingPerson",
                        "name": {"value": "John"},
                        "age": {"value": 42},
                        "cars": {
                            "edges": [
                                {
                                    "node": {
                                        "id": CAR_ID,
                                        "__typename": "TestingCar",
                                        "name": {"value": "Volt"},
                                        "owner": {"node": {"id": PERSON_ID, "__typename": "TestingPerson"}},
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        }
    }

    assert await transform.run(data=data) == {"name": "John", "age": 42}


def _group_with_tag_member_response() -> dict[str, Any]:
    member = {"node": {"id": TAG_ID, "hfid": ["red"], "display_label": "red", "__typename": "BuiltinTag"}}
    return {
        "data": {
            "CoreStandardGroup": {
                "count": 1,
                "edges": [
                    {
                        "node": {
                            "id": GROUP_ID,
                            "display_label": "tracking",
                            "__typename": "CoreStandardGroup",
                            "name": {"value": "tracking"},
                            "members": {"count": 1, "edges": [member]},
                        }
                    }
                ],
            }
        }
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_get_group_with_members_keeps_values_of_node_stored_under_a_key(
    client_type: str, clients: BothClients, schema_query_05_data: dict, httpx_mock: HTTPXMock
) -> None:
    """A group member copy carries only id, hfid and display label; a key set by the user must keep the values.

    The SDK's tracking session runs this query when it updates its group.
    """
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=_group_with_tag_member_response())
    tag_data = {"id": TAG_ID, "name": {"value": "red"}}

    if client_type == "standard":
        client = clients.standard
        client.schema.set_cache(schema=schema_query_05_data, branch="main")
        tag = InfrahubNode(client=client, schema=await client.schema.get(kind="BuiltinTag"), data=tag_data)
        client.store.set(key="red-tag", node=tag)
        await client.get(kind="CoreStandardGroup", name__value="tracking", include=["members"])
    else:
        client = clients.sync
        client.schema.set_cache(schema=schema_query_05_data, branch="main")
        tag = InfrahubNodeSync(client=client, schema=client.schema.get(kind="BuiltinTag"), data=tag_data)
        client.store.set(key="red-tag", node=tag)
        client.get(kind="CoreStandardGroup", name__value="tracking", include=["members"])

    assert client.store.get(key="red-tag").name.value == "red"
