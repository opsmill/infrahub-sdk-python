from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.protocols import CoreRepository, CoreRepositorySync
from infrahub_sdk.protocols_base import CoreNode, CoreNodeSync
from infrahub_sdk.schema import AttributeSchema, NodeSchema
from infrahub_sdk.schema.main import AttributeKind
from infrahub_sdk.store import NodeStore, NodeStoreSync
from infrahub_sdk.timestamp import Timestamp

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.node import RelatedNode, RelatedNodeSync, RelationshipManager, RelationshipManagerSync
    from infrahub_sdk.protocols_base import String, StringOptional
    from infrahub_sdk.schema import NodeSchemaAPI

    from .conftest import BothClients

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

client_types = ["standard", "sync"]

LOCATION_ID = "llllllll-llll-llll-llll-llllllllllll"
TAG_RED_ID = "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr"
TAG_GREEN_ID = "gggggggg-gggg-gggg-gggg-gggggggggggg"
TAG_BLUE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class BuiltinLocation(CoreNode):
    """Typed protocol matching the `location_schema` conftest fixture."""

    name: String
    description: StringOptional
    type: String
    primary_tag: RelatedNode
    tags: RelationshipManager


class BuiltinLocationSync(CoreNodeSync):
    name: String
    description: StringOptional
    type: String
    primary_tag: RelatedNodeSync
    tags: RelationshipManagerSync


def deep_location_data() -> dict[str, Any]:
    """A full fetch: all attributes, the cardinality-one and cardinality-many relationships."""
    return {
        "node": {
            "__typename": "BuiltinLocation",
            "id": LOCATION_ID,
            "display_label": "jfk1",
            "name": {"value": "JFK1"},
            "description": {"value": "JFK Airport"},
            "type": {"value": "SITE"},
            "primary_tag": {
                "node": {"id": TAG_RED_ID, "display_label": "red", "__typename": "BuiltinTag"},
            },
            "tags": {
                "count": 2,
                "edges": [
                    {"node": {"id": TAG_BLUE_ID, "display_label": "blue", "__typename": "BuiltinTag"}},
                    {"node": {"id": TAG_GREEN_ID, "display_label": "green", "__typename": "BuiltinTag"}},
                ],
            },
        }
    }


def shallow_location_data() -> dict[str, Any]:
    """A shallow re-fetch of the same node: only the name attribute, no relationships."""
    return {
        "node": {
            "__typename": "BuiltinLocation",
            "id": LOCATION_ID,
            "display_label": "jfk1",
            "name": {"value": "JFK1"},
        }
    }


def setup_store(
    client_type: str, clients: BothClients
) -> tuple[InfrahubClient | InfrahubClientSync, NodeStore | NodeStoreSync, type[InfrahubNode | InfrahubNodeSync]]:
    if client_type == "standard":
        return clients.standard, NodeStore(default_branch="main"), InfrahubNode
    return clients.sync, NodeStoreSync(default_branch="main"), InfrahubNodeSync


def get_location(store: NodeStore | NodeStoreSync) -> BuiltinLocation | BuiltinLocationSync:
    """Return the stored location through the typed protocol matching the store flavour."""
    if isinstance(store, NodeStore):
        return store.get(key=LOCATION_ID, kind=BuiltinLocation)
    return store.get(key=LOCATION_ID, kind=BuiltinLocationSync)


@pytest.mark.parametrize("client_type", client_types)
def test_merge_keeps_relationships_after_shallow_refetch(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """The ticket regression: a shallow re-fetch must not drop previously fetched relationships."""
    client, store, node_class = setup_store(client_type, clients)

    deep = node_class(client=client, schema=location_schema, data=deep_location_data())
    store.set(node=deep)
    shallow = node_class(client=client, schema=location_schema, data=shallow_location_data())
    store.set(node=shallow)

    stored = get_location(store)
    assert stored is deep
    assert stored.primary_tag.id == TAG_RED_ID
    assert stored.tags.peer_ids == [TAG_BLUE_ID, TAG_GREEN_ID]
    # No duplicate entries: one object, one uuid pointer, stable identity
    branch = store._branches["main"]
    assert len(branch._objs) == 1
    assert branch._uuids[LOCATION_ID] == deep._internal_id


@pytest.mark.parametrize("client_type", client_types)
def test_merge_keeps_attributes_not_refetched(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))
    refetch = shallow_location_data()
    refetch["node"]["name"] = {"value": "JFK2"}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    stored = get_location(store)
    assert stored.name.value == "JFK2"
    assert stored.description.value == "JFK Airport"
    assert stored.type.value == "SITE"


@pytest.mark.parametrize("client_type", client_types)
def test_merge_refreshes_fetched_relationships(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """A re-fetched relationship reflects the server: one-relationship move, many-member removal."""
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))
    refetch = shallow_location_data()
    refetch["node"]["primary_tag"] = {
        "node": {"id": TAG_GREEN_ID, "display_label": "green", "__typename": "BuiltinTag"}
    }
    refetch["node"]["tags"] = {
        "count": 1,
        "edges": [{"node": {"id": TAG_BLUE_ID, "display_label": "blue", "__typename": "BuiltinTag"}}],
    }
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    stored = get_location(store)
    assert stored.primary_tag.id == TAG_GREEN_ID
    assert stored.tags.peer_ids == [TAG_BLUE_ID]


@pytest.mark.parametrize("client_type", client_types)
def test_merge_reflects_cleared_cardinality_one(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """A fetched-but-empty one-relationship clears the stored peer (the move-to-root trap)."""
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))
    refetch = shallow_location_data()
    refetch["node"]["primary_tag"] = {"node": None}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    stored = get_location(store)
    assert stored.primary_tag.id is None
    assert stored.primary_tag.initialized is False
    # Not re-fetched relationships are untouched
    assert stored.tags.peer_ids == [TAG_BLUE_ID, TAG_GREEN_ID]


@pytest.mark.parametrize("client_type", client_types)
def test_merge_fetched_none_attribute_overwrites(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """The presence flag means "present in the response": a genuine server-side clear wins."""
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))
    refetch = shallow_location_data()
    refetch["node"]["description"] = {"value": None}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    assert get_location(store).description.value is None


@pytest.mark.parametrize("client_type", client_types)
def test_merge_local_edits_win(client_type: str, clients: BothClients, location_schema: NodeSchemaAPI) -> None:
    client, store, node_class = setup_store(client_type, clients)

    node = node_class(client=client, schema=location_schema, data=deep_location_data())
    store.set(node=node)
    stored = get_location(store)
    assert stored is node
    stored.description.value = "local edit"
    node.primary_tag = TAG_BLUE_ID

    refetch = deep_location_data()
    refetch["node"]["description"] = {"value": "server edit"}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    assert get_location(store) is node
    assert stored.description.value == "local edit"
    assert stored.primary_tag.id == TAG_BLUE_ID
    # Untouched fields still refresh
    assert stored.name.value == "JFK1"


@pytest.mark.parametrize("client_type", client_types)
def test_merge_false_replaces(client_type: str, clients: BothClients, location_schema: NodeSchemaAPI) -> None:
    """merge=False drops prior knowledge of the node and stores exactly what was fetched."""
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))
    shallow = node_class(client=client, schema=location_schema, data=shallow_location_data())
    store.set(node=shallow, merge=False)

    stored = get_location(store)
    assert stored is shallow
    assert stored.description.value is None
    assert stored.primary_tag.initialized is False
    assert stored.tags.peer_ids == []
    assert len(store._branches["main"]._objs) == 1


@pytest.mark.parametrize("client_type", client_types)
def test_store_default_merge_from_config(client_type: str, clients: BothClients) -> None:
    """The client store default comes from Config.store_merge; merge is the default."""
    if client_type == "standard":
        assert clients.standard.store._default_merge is True
    else:
        assert clients.sync.store._default_merge is True


@pytest.mark.parametrize("client_type", client_types)
def test_merge_refreshes_display_label(client_type: str, clients: BothClients, location_schema: NodeSchemaAPI) -> None:
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))

    # Absent display_label -> kept
    no_label = shallow_location_data()
    del no_label["node"]["display_label"]
    store.set(node=node_class(client=client, schema=location_schema, data=no_label))
    assert get_location(store).display_label == "jfk1"

    # Present display_label -> refreshed
    new_label = shallow_location_data()
    new_label["node"]["display_label"] = "jfk1-renamed"
    store.set(node=node_class(client=client, schema=location_schema, data=new_label))
    assert get_location(store).display_label == "jfk1-renamed"


@pytest.mark.parametrize("client_type", client_types)
def test_merge_value_only_refetch_preserves_attribute_properties(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    client, store, node_class = setup_store(client_type, clients)

    with_properties = deep_location_data()
    with_properties["node"]["name"] = {
        "value": "JFK1",
        "is_protected": True,
        "updated_at": "2024-01-15T10:30:00.000000Z",
        "source": {"id": "ssssssss-ssss-ssss-ssss-ssssssssssss", "display_label": "crm", "__typename": "CoreAccount"},
        "owner": None,
    }
    deep = node_class(client=client, schema=location_schema, data=with_properties)
    store.set(node=deep)

    value_only = shallow_location_data()
    value_only["node"]["name"] = {"value": "JFK2"}
    store.set(node=node_class(client=client, schema=location_schema, data=value_only))

    assert get_location(store) is deep
    stored_name = deep._attribute_data["name"]
    assert stored_name.value == "JFK2"
    assert stored_name.is_protected is True
    assert stored_name.updated_at == "2024-01-15T10:30:00.000000Z"
    assert stored_name.source is not None
    assert stored_name.source.id == "ssssssss-ssss-ssss-ssss-ssssssssssss"


@pytest.mark.parametrize("client_type", client_types)
def test_merge_does_not_mark_attributes_mutated(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """Guards the save path: a merged node must not serialize fields the user never touched."""
    client, store, node_class = setup_store(client_type, clients)

    deep = node_class(client=client, schema=location_schema, data=deep_location_data())
    store.set(node=deep)
    refetch = shallow_location_data()
    refetch["node"]["name"] = {"value": "JFK2"}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    assert get_location(store) is deep
    assert all(attr.value_has_been_mutated is False for attr in deep._attribute_data.values())


@pytest.mark.parametrize("client_type", client_types)
def test_merge_reindexes_hfid(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    """When an hfid-component attribute refreshes, the hfid index follows and drops the stale entry."""
    client, store, node_class = setup_store(client_type, clients)
    schema = schema_with_hfid["location"]

    store.set(node=node_class(client=client, schema=schema, data=deep_location_data()))
    assert store.get(key="BuiltinLocation__JFK1").id == LOCATION_ID

    refetch = shallow_location_data()
    refetch["node"]["name"] = {"value": "JFK2"}
    store.set(node=node_class(client=client, schema=schema, data=refetch))

    assert store.get(key="BuiltinLocation__JFK2").id == LOCATION_ID
    assert store.get(key="BuiltinLocation__JFK1", raise_when_missing=False) is None


@pytest.mark.parametrize("client_type", client_types)
def test_merge_custom_key_points_to_merged_object(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()), key="mykey")
    store.set(node=node_class(client=client, schema=location_schema, data=shallow_location_data()))

    assert store.get(key="mykey") is store.get(key=LOCATION_ID)


@pytest.mark.parametrize("client_type", client_types)
def test_kind_change_replaces_wholesale(
    client_type: str, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]
) -> None:
    """The same uuid arriving as another kind (ConvertObjectType) replaces the entry, even in merge mode."""
    client, store, node_class = setup_store(client_type, clients)

    location = node_class(client=client, schema=schema_with_hfid["location"], data=deep_location_data())
    store.set(node=location, key="mykey")
    assert store.get(key="BuiltinLocation__JFK1").id == LOCATION_ID

    converted_data = {
        "node": {
            "__typename": "BuiltinRack",
            "id": LOCATION_ID,
            "display_label": "jfk1",
            "facility_id": {"value": "JFK1"},
        }
    }
    converted = node_class(client=client, schema=schema_with_hfid["rack"], data=converted_data)
    store.set(node=converted)

    stored = store.get(key=LOCATION_ID)
    assert stored is converted
    assert stored.get_kind() == "BuiltinRack"
    assert len(store._branches["main"]._objs) == 1
    # The old kind's hfid index no longer points at the discarded object
    assert store.get(key="BuiltinLocation__JFK1", raise_when_missing=False) is None
    # Custom keys follow the replacement
    assert store.get(key="mykey") is converted


@pytest.mark.parametrize("client_type", client_types)
def test_merge_same_peer_keeps_identity_details_not_carried(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """A narrow payload for the same peer must not null previously fetched identity data."""
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))
    refetch = shallow_location_data()
    refetch["node"]["primary_tag"] = {"node": {"id": TAG_RED_ID}}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    stored = get_location(store)
    assert stored.primary_tag.id == TAG_RED_ID
    assert stored.primary_tag.display_label == "red"
    assert stored.primary_tag.typename == "BuiltinTag"


@pytest.mark.parametrize("client_type", client_types)
def test_merge_clears_pool_allocation_intent_on_refetch(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """A fetched value clears a stale from_pool request.

    A surviving from_pool would take precedence over the value in the next mutation
    payload and trigger a re-allocation.
    """
    client, store, node_class = setup_store(client_type, clients)

    pool_data = deep_location_data()
    pool_data["node"]["description"] = {"from_pool": {"id": "pppppppp-pppp-pppp-pppp-pppppppppppp"}}
    stored_node = node_class(client=client, schema=location_schema, data=pool_data)
    assert stored_node._attribute_data["description"]._from_pool is not None
    store.set(node=stored_node)

    refetch = shallow_location_data()
    refetch["node"]["description"] = {"value": "allocated-value"}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    assert get_location(store) is stored_node
    assert stored_node._attribute_data["description"].value == "allocated-value"
    assert stored_node._attribute_data["description"]._from_pool is None


@pytest.mark.parametrize("client_type", client_types)
def test_merge_peer_change_drops_old_edge_properties(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """A changed peer is a different edge: the old edge's properties must not survive."""
    client, store, node_class = setup_store(client_type, clients)

    with_properties = deep_location_data()
    with_properties["node"]["primary_tag"] = {
        "properties": {
            "is_protected": True,
            "source": {
                "id": "ssssssss-ssss-ssss-ssss-ssssssssssss",
                "display_label": "crm",
                "__typename": "CoreAccount",
            },
        },
        "node": {"id": TAG_RED_ID, "display_label": "red", "__typename": "BuiltinTag"},
    }
    store.set(node=node_class(client=client, schema=location_schema, data=with_properties))

    refetch = shallow_location_data()
    refetch["node"]["primary_tag"] = {
        "node": {"id": TAG_GREEN_ID, "display_label": "green", "__typename": "BuiltinTag"}
    }
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    stored = get_location(store)
    assert stored.primary_tag.id == TAG_GREEN_ID
    assert stored.primary_tag.is_protected is None
    assert stored.primary_tag.source is None


@pytest.mark.parametrize("client_type", client_types)
def test_merge_clears_hfid_only_relationship(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """A cleared relationship tracked only by hfid (no id on either side) is reflected."""
    client, store, node_class = setup_store(client_type, clients)

    hfid_only = deep_location_data()
    hfid_only["node"]["primary_tag"] = {"node": {"hfid": ["red"], "__typename": "BuiltinTag"}}
    store.set(node=node_class(client=client, schema=location_schema, data=hfid_only))
    assert get_location(store).primary_tag.hfid == ["red"]

    refetch = shallow_location_data()
    refetch["node"]["primary_tag"] = {"node": None}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))

    stored = get_location(store)
    assert stored.primary_tag.hfid is None
    assert stored.primary_tag.initialized is False


@pytest.mark.parametrize("client_type", client_types)
def test_merge_propagates_unsaved_edits(client_type: str, clients: BothClients, location_schema: NodeSchemaAPI) -> None:
    """Unsaved edits merged into the store keep their pending-mutation markers.

    A later save of the merged store copy must still send them.
    """
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))

    incoming = node_class(client=client, schema=location_schema, data=deep_location_data())
    incoming._attribute_data["description"].value = None
    incoming.primary_tag = TAG_GREEN_ID
    incoming._relationship_cardinality_many_data["tags"].add(TAG_RED_ID)
    store.set(node=incoming)

    stored = get_location(store)
    assert stored is not incoming
    assert stored.description.value is None
    assert stored.name.value == "JFK1"
    inner = store.get(key=LOCATION_ID)
    assert inner._attribute_data["description"].value_has_been_mutated is True
    assert inner._attribute_data["name"].value_has_been_mutated is False
    assert stored.primary_tag.id == TAG_GREEN_ID
    assert inner._relationship_cardinality_one_data["primary_tag"]._peer_has_been_mutated is True
    assert TAG_RED_ID in stored.tags.peer_ids
    assert stored.tags.has_update is True


@pytest.mark.parametrize("client_type", client_types)
async def test_update_resets_mutation_tracking(
    httpx_mock: HTTPXMock, client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """A successful mutation marks the in-memory state as persisted.

    The store can then refresh those fields from later fetches instead of protecting
    them as pending local edits forever.
    """
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinLocationUpdate": {"ok": True, "object": {"id": LOCATION_ID}}}},
    )
    client, store, node_class = setup_store(client_type, clients)

    node = node_class(client=client, schema=location_schema, data=deep_location_data())
    node._attribute_data["description"].value = "edited"
    node.primary_tag = TAG_GREEN_ID
    node._relationship_cardinality_many_data["tags"].add(TAG_RED_ID)
    if isinstance(node, InfrahubNode):
        await node.update()
    else:
        node.update()

    assert node._attribute_data["description"].value_has_been_mutated is False
    assert node._relationship_cardinality_one_data["primary_tag"]._peer_has_been_mutated is False
    assert node._relationship_cardinality_many_data["tags"].has_update is False

    # The saved field is persisted state now: a later fetch refreshes it in the store
    store.set(node=node)
    refetch = shallow_location_data()
    refetch["node"]["description"] = {"value": "server refresh"}
    store.set(node=node_class(client=client, schema=location_schema, data=refetch))
    assert get_location(store).description.value == "server refresh"


@pytest.mark.parametrize("client_type", client_types)
def test_fetched_fields_are_interned(client_type: str, clients: BothClients, location_schema: NodeSchemaAPI) -> None:
    """Attributes built from the same query shape share one presence frozenset."""
    client, _, node_class = setup_store(client_type, clients)

    first = node_class(client=client, schema=location_schema, data=deep_location_data())
    second = node_class(client=client, schema=location_schema, data=deep_location_data())

    assert first._attribute_data["name"]._fetched_fields is second._attribute_data["name"]._fetched_fields
    assert (
        first._relationship_cardinality_one_data["primary_tag"]._fetched_properties
        is second._relationship_cardinality_one_data["primary_tag"]._fetched_properties
    )


@pytest.mark.parametrize("client_type", client_types)
def test_merge_keeps_data_baseline_in_sync(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """The raw _data baseline used by update() diffs merges key-wise like the attributes."""
    client, store, node_class = setup_store(client_type, clients)

    with_properties = deep_location_data()
    with_properties["node"]["name"] = {"value": "JFK1", "is_protected": True}
    deep = node_class(client=client, schema=location_schema, data=with_properties)
    store.set(node=deep)

    value_only = shallow_location_data()
    value_only["node"]["name"] = {"value": "JFK2"}
    store.set(node=node_class(client=client, schema=location_schema, data=value_only))

    assert get_location(store) is deep
    assert isinstance(deep._data, dict)
    assert deep._data["name"] == {"value": "JFK2", "is_protected": True}


@pytest.mark.parametrize("client_type", client_types)
def test_merge_presence_detection_with_aliased_fields(
    client_type: str, clients: BothClients, location_schema: NodeSchemaAPI
) -> None:
    """Presence detection still fires when fields arrive under aliases normalised by _strip_alias."""
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=location_schema, data=deep_location_data()))

    aliased = {
        "node": {
            "__typename": "BuiltinLocation",
            "id": LOCATION_ID,
            "attr__alias__name": {"value": "JFK2"},
        }
    }
    refetch = node_class(client=client, schema=location_schema, data=node_class._strip_alias(aliased))
    assert refetch._attribute_data["name"].is_fetched is True
    store.set(node=refetch)

    stored = get_location(store)
    assert stored.name.value == "JFK2"
    assert stored.description.value == "JFK Airport"


HIERARCHY_ID = "hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh"
PARENT_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PARENT_B_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CHILD_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"


class InfraLocation(CoreNode):
    """Typed protocol matching the hierarchical schema fixture below."""

    name: String
    description: StringOptional
    parent: RelatedNode
    children: RelationshipManager
    ancestors: RelationshipManager
    descendants: RelationshipManager


class InfraLocationSync(CoreNodeSync):
    name: String
    description: StringOptional
    parent: RelatedNodeSync
    children: RelationshipManagerSync
    ancestors: RelationshipManagerSync
    descendants: RelationshipManagerSync


def get_hierarchical_location(store: NodeStore | NodeStoreSync) -> InfraLocation | InfraLocationSync:
    if isinstance(store, NodeStore):
        return store.get(key=HIERARCHY_ID, kind=InfraLocation)
    return store.get(key=HIERARCHY_ID, kind=InfraLocationSync)


@pytest.fixture
async def hierarchical_location_schema() -> NodeSchemaAPI:
    schema = NodeSchema(
        name="Location",
        namespace="Infra",
        default_filter="name__value",
        attributes=[
            AttributeSchema(name="name", kind=AttributeKind.TEXT, unique=True),
            AttributeSchema(name="description", kind=AttributeKind.TEXT, optional=True),
        ],
        relationships=[],
    )
    schema_api = schema.convert_api()
    schema_api.hierarchy = "InfraLocation"
    return schema_api


def deep_hierarchical_data() -> dict[str, Any]:
    return {
        "node": {
            "__typename": "InfraLocation",
            "id": HIERARCHY_ID,
            "display_label": "california",
            "name": {"value": "California"},
            "parent": {"node": {"id": PARENT_A_ID, "display_label": "USA", "__typename": "InfraLocation"}},
            "children": {
                "count": 1,
                "edges": [{"node": {"id": CHILD_ID, "display_label": "Yolo County", "__typename": "InfraLocation"}}],
            },
            "ancestors": {
                "count": 1,
                "edges": [{"node": {"id": PARENT_A_ID, "display_label": "USA", "__typename": "InfraLocation"}}],
            },
            "descendants": {
                "count": 1,
                "edges": [{"node": {"id": CHILD_ID, "display_label": "Yolo County", "__typename": "InfraLocation"}}],
            },
        }
    }


def shallow_hierarchical_data() -> dict[str, Any]:
    return {
        "node": {
            "__typename": "InfraLocation",
            "id": HIERARCHY_ID,
            "display_label": "california",
            "name": {"value": "California"},
        }
    }


@pytest.mark.parametrize("client_type", client_types)
def test_merge_keeps_hierarchical_fields_after_shallow_refetch(
    client_type: str, clients: BothClients, hierarchical_location_schema: NodeSchemaAPI
) -> None:
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=hierarchical_location_schema, data=deep_hierarchical_data()))
    store.set(node=node_class(client=client, schema=hierarchical_location_schema, data=shallow_hierarchical_data()))

    stored = get_hierarchical_location(store)
    assert stored.parent.id == PARENT_A_ID
    assert stored.children.peer_ids == [CHILD_ID]
    assert stored.ancestors.peer_ids == [PARENT_A_ID]
    assert stored.descendants.peer_ids == [CHILD_ID]


@pytest.mark.parametrize("client_type", client_types)
def test_merge_reflects_hierarchical_parent_move(
    client_type: str, clients: BothClients, hierarchical_location_schema: NodeSchemaAPI
) -> None:
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=hierarchical_location_schema, data=deep_hierarchical_data()))
    refetch = shallow_hierarchical_data()
    refetch["node"]["parent"] = {"node": {"id": PARENT_B_ID, "display_label": "Canada", "__typename": "InfraLocation"}}
    store.set(node=node_class(client=client, schema=hierarchical_location_schema, data=refetch))

    assert get_hierarchical_location(store).parent.id == PARENT_B_ID


@pytest.mark.parametrize("client_type", client_types)
def test_merge_reflects_hierarchical_move_to_root(
    client_type: str, clients: BothClients, hierarchical_location_schema: NodeSchemaAPI
) -> None:
    """The RelatedNode.initialized trap: a fetched-but-empty parent must clear the stored one."""
    client, store, node_class = setup_store(client_type, clients)

    store.set(node=node_class(client=client, schema=hierarchical_location_schema, data=deep_hierarchical_data()))
    refetch = shallow_hierarchical_data()
    refetch["node"]["parent"] = {"node": None}
    store.set(node=node_class(client=client, schema=hierarchical_location_schema, data=refetch))

    stored = get_hierarchical_location(store)
    assert stored.parent.id is None
    # Children were not re-fetched and are kept
    assert stored.children.peer_ids == [CHILD_ID]


REPOSITORY_ID = "bfae43e8-5ebb-456c-a946-bf64e930710a"
REPOSITORY_LOCATION = "git@github.com:opsmill/infrahub-demo-core.git"


def repository_response(include_location: bool = True) -> dict[str, Any]:
    node: dict[str, Any] = {
        "__typename": "CoreRepository",
        "id": REPOSITORY_ID,
        "name": {"value": "infrahub-demo-core"},
    }
    if include_location:
        node["location"] = {"value": REPOSITORY_LOCATION}
    return {"data": {"CoreRepository": {"edges": [{"node": node}]}}}


@pytest.mark.parametrize("client_type", client_types)
async def test_query_merges_into_store_and_returns_per_query_object(
    httpx_mock: HTTPXMock, clients: BothClients, mock_schema_query_01: HTTPXMock, client_type: str
) -> None:
    """Queries hand you what you asked for; the store remembers the union of everything it has seen."""
    httpx_mock.add_response(
        method="POST",
        json=repository_response(include_location=True),
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
    )
    httpx_mock.add_response(
        method="POST",
        json=repository_response(include_location=False),
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
    )

    first: CoreRepository | CoreRepositorySync
    second: CoreRepository | CoreRepositorySync
    stored: CoreRepository | CoreRepositorySync
    if client_type == "standard":
        first = await clients.standard.get(kind=CoreRepository, id=REPOSITORY_ID)
        second = await clients.standard.get(kind=CoreRepository, id=REPOSITORY_ID, exclude=["location"])
        stored = clients.standard.store.get(key=REPOSITORY_ID, kind=CoreRepository)
    else:
        first = clients.sync.get(kind=CoreRepositorySync, id=REPOSITORY_ID)
        second = clients.sync.get(kind=CoreRepositorySync, id=REPOSITORY_ID, exclude=["location"])
        stored = clients.sync.store.get(key=REPOSITORY_ID, kind=CoreRepositorySync)

    # The store holds the merged canonical copy
    assert stored is first
    assert stored.location.value == REPOSITORY_LOCATION
    # The second query returns a per-query snapshot, not the merged store object
    assert second is not stored
    assert second == stored
    assert second.location.value is None


@pytest.mark.parametrize("client_type", client_types)
async def test_consistent_at_queries_populate_and_merge(
    httpx_mock: HTTPXMock, clients: BothClients, mock_schema_query_01: HTTPXMock, client_type: str
) -> None:
    """A script running all its queries at one timestamp gets full store functionality."""
    httpx_mock.add_response(
        method="POST",
        json=repository_response(include_location=True),
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
    )
    httpx_mock.add_response(
        method="POST",
        json=repository_response(include_location=False),
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
    )

    stored: CoreRepository | CoreRepositorySync
    # Two distinct Timestamp objects for the same instant share one store context
    if client_type == "standard":
        await clients.standard.get(kind=CoreRepository, id=REPOSITORY_ID, at=Timestamp("2023-01-01T00:00:00Z"))
        await clients.standard.get(
            kind=CoreRepository, id=REPOSITORY_ID, at=Timestamp("2023-01-01T00:00:00Z"), exclude=["location"]
        )
        stored = clients.standard.store.get(key=REPOSITORY_ID, kind=CoreRepository)
    else:
        clients.sync.get(kind=CoreRepositorySync, id=REPOSITORY_ID, at=Timestamp("2023-01-01T00:00:00Z"))
        clients.sync.get(
            kind=CoreRepositorySync, id=REPOSITORY_ID, at=Timestamp("2023-01-01T00:00:00Z"), exclude=["location"]
        )
        stored = clients.sync.store.get(key=REPOSITORY_ID, kind=CoreRepositorySync)

    # The shallow historical re-fetch merged instead of replacing: no data lost
    assert stored.location.value == REPOSITORY_LOCATION


@pytest.mark.parametrize("client_type", client_types)
async def test_at_query_after_live_context_skips_store_with_warning(
    httpx_mock: HTTPXMock, clients: BothClients, mock_schema_query_01: HTTPXMock, client_type: str
) -> None:
    """A historical read must not blend into a live cache: it warns and skips the store."""
    httpx_mock.add_response(
        method="POST",
        json=repository_response(include_location=True),
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
    )
    httpx_mock.add_response(
        method="POST",
        json=repository_response(include_location=False),
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
    )

    at = Timestamp("2023-01-01T00:00:00Z")
    stored: CoreRepository | CoreRepositorySync
    if client_type == "standard":
        await clients.standard.get(kind=CoreRepository, id=REPOSITORY_ID)
        with pytest.warns(UserWarning, match="Mixing timestamps"):
            node = await clients.standard.get(kind=CoreRepository, id=REPOSITORY_ID, at=at)
        stored = clients.standard.store.get(key=REPOSITORY_ID, kind=CoreRepository)
    else:
        clients.sync.get(kind=CoreRepositorySync, id=REPOSITORY_ID)
        with pytest.warns(UserWarning, match="Mixing timestamps"):
            node = clients.sync.get(kind=CoreRepositorySync, id=REPOSITORY_ID, at=at)
        stored = clients.sync.store.get(key=REPOSITORY_ID, kind=CoreRepositorySync)

    # The historical query still returned its result, but the live cache is untouched
    assert node.id == REPOSITORY_ID
    assert stored.location.value == REPOSITORY_LOCATION


@pytest.mark.parametrize("client_type", client_types)
async def test_live_query_after_at_context_skips_store_with_warning(
    httpx_mock: HTTPXMock, clients: BothClients, mock_schema_query_01: HTTPXMock, client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        json=repository_response(include_location=True),
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
    )
    httpx_mock.add_response(
        method="POST",
        json=repository_response(include_location=False),
        match_headers={"X-Infrahub-Tracker": "query-corerepository-page1"},
    )

    at = Timestamp("2023-01-01T00:00:00Z")
    stored: CoreRepository | CoreRepositorySync
    if client_type == "standard":
        await clients.standard.get(kind=CoreRepository, id=REPOSITORY_ID, at=at)
        with pytest.warns(UserWarning, match="Mixing timestamps"):
            await clients.standard.get(kind=CoreRepository, id=REPOSITORY_ID)
        stored = clients.standard.store.get(key=REPOSITORY_ID, kind=CoreRepository)
    else:
        clients.sync.get(kind=CoreRepositorySync, id=REPOSITORY_ID, at=at)
        with pytest.warns(UserWarning, match="Mixing timestamps"):
            clients.sync.get(kind=CoreRepositorySync, id=REPOSITORY_ID)
        stored = clients.sync.store.get(key=REPOSITORY_ID, kind=CoreRepositorySync)

    # The store keeps the historical context it was stamped with
    assert stored.location.value == REPOSITORY_LOCATION
