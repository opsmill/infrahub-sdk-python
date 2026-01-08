import pytest

from infrahub_sdk.client import InfrahubClient
from infrahub_sdk.exceptions import NodeNotFoundError
from infrahub_sdk.node import InfrahubNode
from infrahub_sdk.schema import NodeSchemaAPI
from infrahub_sdk.store import NodeStoreBranch


def test_node_store_set(client: InfrahubClient, schema_with_hfid: dict[str, NodeSchemaAPI]) -> None:
    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    node = InfrahubNode(client=client, schema=schema_with_hfid["location"], data=data)

    store = NodeStoreBranch(name="mybranch")
    store.set(key="mykey", node=node)

    assert node._internal_id in store._objs
    assert "mykey" in store._keys
    assert store._keys["mykey"] == node._internal_id


def test_node_store_set_no_hfid(client: InfrahubClient, location_schema: NodeSchemaAPI) -> None:
    data = {
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    node = InfrahubNode(client=client, schema=location_schema, data=data)

    store = NodeStoreBranch(name="mybranch")

    store.set(key="mykey", node=node)

    assert node._internal_id in store._objs
    assert "mykey" in store._keys
    assert store._keys["mykey"] == node._internal_id


def test_node_store_get(client: InfrahubClient, location_schema: NodeSchemaAPI) -> None:
    data = {
        "id": "54f3108c-1f21-44c4-93cf-ec5737587b48",
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    node = InfrahubNode(client=client, schema=location_schema, data=data)

    store = NodeStoreBranch(name="mybranch")

    store.set(key="mykey", node=node)

    assert store.get(key=node._internal_id).id == node.id
    assert store.get(kind="BuiltinLocation", key="mykey").id == node.id
    assert store.get(key="mykey").id == node.id

    assert store.get(kind="BuiltinLocation", key="anotherkey", raise_when_missing=False) is None
    assert store.get(key="anotherkey", raise_when_missing=False) is None

    with pytest.raises(NodeNotFoundError):
        store.get(kind="BuiltinLocation", key="anotherkey")
    with pytest.raises(NodeNotFoundError):
        store.get(key="anotherkey")


def test_node_store_get_with_hfid(client: InfrahubClient, schema_with_hfid: dict[str, NodeSchemaAPI]) -> None:
    data = {
        "id": "54f3108c-1f21-44c4-93cf-ec5737587b48",
        "name": {"value": "JFK1"},
        "description": {"value": "JFK Airport"},
        "type": {"value": "SITE"},
    }
    node = InfrahubNode(client=client, schema=schema_with_hfid["location"], data=data)

    store = NodeStoreBranch(name="mybranch")

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
