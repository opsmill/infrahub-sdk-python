import pytest

from infrahub_sdk.exceptions import NodeInvalidError, NodeNotFoundError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.store import NodeStore, NodeStoreSync

client_types = ["standard", "sync"]


@pytest.mark.parametrize("client_type", client_types)
def test_node_store_set(client_type, clients, schema_with_hfid) -> None:
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
def test_node_store_set_no_hfid(client_type, clients, location_schema) -> None:
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
def test_node_store_get(client_type, clients, location_schema) -> None:
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
def test_node_store_get_with_hfid(client_type, clients, schema_with_hfid) -> None:
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
