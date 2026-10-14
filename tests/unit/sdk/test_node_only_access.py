from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import Error, UninitializedError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.node.attribute import Attribute
from infrahub_sdk.node.related_node import RelatedNode, RelatedNodeSync
from infrahub_sdk.node.relationship import RelationshipManager, RelationshipManagerSync
from infrahub_sdk.schema import NodeSchema, NodeSchemaAPI, SchemaRootAPI

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from .conftest import BothClients

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

client_types = ["standard", "sync"]

LOCATION_ID = "llllllll-llll-llll-llll-llllllllllll"
TAG_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
LOCATION_FIELDS = ("name", "description", "type", "primary_tag", "tags", "member_of_groups")
HIERARCHY_FIELDS = ("parent", "children", "ancestors", "descendants")
TAG_PEER = {"node": {"id": TAG_ID, "display_label": "blue", "__typename": "BuiltinTag"}}

AnyNode = InfrahubNode | InfrahubNodeSync


def build_node(clients: BothClients, client_type: str, schema: NodeSchemaAPI, data: dict[str, Any] | None) -> AnyNode:
    if client_type == "standard":
        return InfrahubNode(client=clients.standard, schema=schema, data=data)
    return InfrahubNodeSync(client=clients.sync, schema=schema, data=data)


def loaded_fields(node: AnyNode, names: tuple[str, ...]) -> dict[str, bool]:
    return {name: getattr(node, name).is_loaded for name in names}


def every_field(loaded: bool, names: tuple[str, ...] = LOCATION_FIELDS) -> dict[str, bool]:
    return dict.fromkeys(names, loaded)


def only_these_fields(*loaded: str, names: tuple[str, ...] = LOCATION_FIELDS) -> dict[str, bool]:
    return {name: name in loaded for name in names}


def hierarchical_location_schema(declares_parent_and_children: bool) -> NodeSchemaAPI:
    relationships = [
        {"name": "parent", "peer": "InfraLocation", "optional": True, "cardinality": "one", "kind": "Hierarchy"},
        {"name": "children", "peer": "InfraLocation", "optional": True, "cardinality": "many", "kind": "Hierarchy"},
    ]
    schema = NodeSchema(
        name="Location",
        namespace="Infra",
        attributes=[{"name": "name", "kind": "Text"}],
        relationships=relationships if declares_parent_and_children else [],
    ).convert_api()
    # `hierarchy` exists only on the API schema, where the server sets it.
    schema.hierarchy = "InfraLocation"
    return schema


@dataclass
class RecordCase:
    name: str
    data: dict[str, Any]
    expected: dict[str, bool]


RECORD_CASES = [
    RecordCase(
        name="every-field-in-data",
        data={
            "id": LOCATION_ID,
            "name": {"value": "DFW"},
            "description": {"value": "Dallas"},
            "type": {"value": "SITE"},
            "primary_tag": TAG_PEER,
            "tags": {"count": 1, "edges": [TAG_PEER]},
            "member_of_groups": {"count": 0, "edges": []},
        },
        expected=every_field(loaded=True),
    ),
    RecordCase(name="only-the-id-in-data", data={"id": LOCATION_ID}, expected=every_field(loaded=False)),
    RecordCase(
        name="attribute-with-a-null-value",
        data={"id": LOCATION_ID, "description": {"value": None}},
        expected=only_these_fields("description"),
    ),
    RecordCase(
        name="cardinality-one-without-a-peer",
        data={"id": LOCATION_ID, "primary_tag": {"node": None}},
        expected=only_these_fields("primary_tag"),
    ),
    RecordCase(
        name="cardinality-many-without-peers",
        data={"id": LOCATION_ID, "tags": {"count": 0, "edges": []}},
        expected=only_these_fields("tags"),
    ),
    RecordCase(
        name="response-wrapped-in-node",
        data={"node": {"id": LOCATION_ID, "name": {"value": "DFW"}, "primary_tag": TAG_PEER}},
        expected=only_these_fields("name", "primary_tag"),
    ),
    RecordCase(
        name="values-given-as-arguments",
        data={"id": LOCATION_ID, "name": "DFW", "primary_tag": TAG_ID, "tags": [TAG_ID]},
        expected=only_these_fields("name", "primary_tag", "tags"),
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in RECORD_CASES])
def test_is_loaded_follows_the_fields_in_the_data(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, case: RecordCase
) -> None:
    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data=case.data)

    assert loaded_fields(node=node, names=LOCATION_FIELDS) == case.expected


@pytest.mark.parametrize("client_type", client_types)
async def test_is_loaded_reads_the_field_names_without_their_alias(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {
        "node": {
            "id": LOCATION_ID,
            "__typename": "BuiltinLocation",
            "__alias__BuiltinLocation__description": {"value": "Dallas"},
            "__alias__BuiltinLocation__primary_tag": TAG_PEER,
        }
    }
    if client_type == "standard":
        node: AnyNode = await InfrahubNode.from_graphql(
            client=clients.standard, branch="main", data=data, schema=location_schema
        )
    else:
        node = InfrahubNodeSync.from_graphql(client=clients.sync, branch="main", data=data, schema=location_schema)

    assert loaded_fields(node=node, names=LOCATION_FIELDS) == only_these_fields("description", "primary_tag")


@dataclass
class HierarchyCase:
    name: str
    declares_parent_and_children: bool
    data: dict[str, Any]
    expected: dict[str, bool]


HIERARCHY_DATA = {
    "id": LOCATION_ID,
    "parent": {"node": {"id": "parent-1", "__typename": "InfraLocation", "display_label": "USA"}},
    "children": {"count": 1, "edges": [{"node": {"id": "child-1", "__typename": "InfraLocation"}}]},
    "ancestors": {"count": 1, "edges": [{"node": {"id": "parent-1", "__typename": "InfraLocation"}}]},
    "descendants": {"count": 0, "edges": []},
}

HIERARCHY_CASES = [
    HierarchyCase(
        name="declared-hierarchy-fields-in-data",
        declares_parent_and_children=True,
        data=HIERARCHY_DATA,
        expected=every_field(loaded=True, names=HIERARCHY_FIELDS),
    ),
    HierarchyCase(
        name="declared-hierarchy-fields-not-in-data",
        declares_parent_and_children=True,
        data={"id": LOCATION_ID},
        expected=every_field(loaded=False, names=HIERARCHY_FIELDS),
    ),
    HierarchyCase(
        name="declared-parent-without-a-peer",
        declares_parent_and_children=True,
        data={"id": LOCATION_ID, "parent": {"node": None}},
        expected=only_these_fields("parent", names=HIERARCHY_FIELDS),
    ),
    HierarchyCase(
        name="hierarchy-fields-in-data",
        declares_parent_and_children=False,
        data=HIERARCHY_DATA,
        expected=every_field(loaded=True, names=HIERARCHY_FIELDS),
    ),
    HierarchyCase(
        name="hierarchy-fields-not-in-data",
        declares_parent_and_children=False,
        data={"id": LOCATION_ID},
        expected=every_field(loaded=False, names=HIERARCHY_FIELDS),
    ),
    HierarchyCase(
        name="ancestors-and-descendants-in-data",
        declares_parent_and_children=False,
        data={"id": LOCATION_ID, "ancestors": HIERARCHY_DATA["ancestors"], "descendants": {"edges": []}},
        expected=only_these_fields("ancestors", "descendants", names=HIERARCHY_FIELDS),
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in HIERARCHY_CASES])
def test_is_loaded_follows_the_hierarchy_fields_in_the_data(
    clients: BothClients, client_type: str, case: HierarchyCase
) -> None:
    schema = hierarchical_location_schema(declares_parent_and_children=case.declares_parent_and_children)
    node = build_node(clients=clients, client_type=client_type, schema=schema, data=case.data)

    assert {name: node._hierarchical_data[name].is_loaded for name in HIERARCHY_FIELDS} == case.expected
    if case.declares_parent_and_children:
        assert node._get_relationship_one("parent").is_loaded is case.expected["parent"]
        assert node._get_relationship_many("children").is_loaded is case.expected["children"]


def assign_value_on_the_attribute(node: AnyNode) -> None:
    node._get_attribute("description").value = "Dallas"


def assign_value_through_the_node(node: AnyNode) -> None:
    node.description = "Dallas"


def assign_none_through_the_node(node: AnyNode) -> None:
    node.description = None


def assign_peer(node: AnyNode) -> None:
    node.primary_tag = TAG_ID


def clear_peer(node: AnyNode) -> None:
    node.primary_tag = None


def assign_peers(node: AnyNode) -> None:
    node._get_relationship_many("tags").peers = []


@dataclass
class AssignmentCase:
    name: str
    assign: Callable[[AnyNode], None]
    field: str


ASSIGNMENT_CASES = [
    AssignmentCase(name="attribute-value-on-the-attribute", assign=assign_value_on_the_attribute, field="description"),
    AssignmentCase(name="attribute-value-through-the-node", assign=assign_value_through_the_node, field="description"),
    AssignmentCase(name="attribute-none-through-the-node", assign=assign_none_through_the_node, field="description"),
    AssignmentCase(name="cardinality-one-peer", assign=assign_peer, field="primary_tag"),
    AssignmentCase(name="cardinality-one-cleared", assign=clear_peer, field="primary_tag"),
    AssignmentCase(name="cardinality-many-peers", assign=assign_peers, field="tags"),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in ASSIGNMENT_CASES])
def test_assignment_makes_the_field_loaded(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, case: AssignmentCase
) -> None:
    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data={"id": LOCATION_ID})
    assert loaded_fields(node=node, names=LOCATION_FIELDS) == every_field(loaded=False)

    case.assign(node)

    assert loaded_fields(node=node, names=LOCATION_FIELDS) == only_these_fields(case.field)


@pytest.mark.parametrize("client_type", client_types)
def test_assigning_peers_keeps_the_list_and_the_initialized_flag(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data={"id": LOCATION_ID})
    tags = node._get_relationship_many("tags")
    new_peers: list[Any] = []

    tags.peers = new_peers

    assert tags.peers is new_peers
    assert tags.is_loaded is True
    assert tags.initialized is False


@pytest.mark.parametrize("client_type", client_types)
def test_peers_returns_the_stored_list(clients: BothClients, location_schema: NodeSchemaAPI, client_type: str) -> None:
    data = {"id": LOCATION_ID, "tags": {"count": 1, "edges": [TAG_PEER]}}
    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data=data)
    tags = node._get_relationship_many("tags")

    tags.peers.clear()

    assert tags.peers == []
    assert tags.peer_ids == []


@pytest.mark.parametrize("client_type", client_types)
async def test_fetch_on_a_manager_makes_it_loaded(
    httpx_mock: HTTPXMock,
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    tag_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "BuiltinLocation": {
                    "count": 1,
                    "edges": [
                        {
                            "node": {
                                "id": LOCATION_ID,
                                "display_label": "dfw1",
                                "__typename": "BuiltinLocation",
                                "tags": {"count": 1, "edges": [TAG_PEER]},
                            }
                        }
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-builtinlocation-page1"},
    )
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "BuiltinTag": {
                    "count": 1,
                    "edges": [
                        {
                            "node": {
                                "id": TAG_ID,
                                "display_label": "blue",
                                "__typename": "BuiltinTag",
                                "name": {"value": "blue"},
                                "description": {"value": None},
                            }
                        }
                    ],
                }
            }
        },
        match_headers={"X-Infrahub-Tracker": "query-builtintag-page1"},
    )
    httpx_mock.add_response(method="POST", json={"data": {"BuiltinTag": {"count": 1}}})
    schema = SchemaRootAPI(nodes=[location_schema, tag_schema])
    clients.standard.schema.set_cache(schema=schema)
    clients.sync.schema.set_cache(schema=schema)

    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data={"id": LOCATION_ID})
    tags = node._get_relationship_many("tags")
    assert tags.is_loaded is False

    if isinstance(tags, RelationshipManager):
        await tags.fetch()
    else:
        tags.fetch()

    assert tags.is_loaded is True
    assert tags.peer_ids == [TAG_ID]
    assert len([request for request in httpx_mock.get_requests() if request.method == "POST"]) == 3


@pytest.mark.parametrize("client_type", client_types)
async def test_new_node_reports_every_field_loaded_until_it_is_saved(
    httpx_mock: HTTPXMock, clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinLocationCreate": {"ok": True, "object": {"id": LOCATION_ID}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-builtinlocation-create"},
    )
    schema = SchemaRootAPI(nodes=[location_schema])
    clients.standard.schema.set_cache(schema=schema)
    clients.sync.schema.set_cache(schema=schema)

    node: AnyNode
    if client_type == "standard":
        node = await clients.standard.create(kind="BuiltinLocation", name="JFK1", type="SITE")
        assert loaded_fields(node=node, names=LOCATION_FIELDS) == every_field(loaded=True)
        await node.save()
    else:
        node = clients.sync.create(kind="BuiltinLocation", name="JFK1", type="SITE")
        assert loaded_fields(node=node, names=LOCATION_FIELDS) == every_field(loaded=True)
        node.save()

    assert node.id == LOCATION_ID
    assert loaded_fields(node=node, names=LOCATION_FIELDS) == only_these_fields("name", "type")


@pytest.mark.parametrize("client_type", client_types)
def test_peers_inside_a_manager_are_loaded(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    data = {"id": LOCATION_ID, "tags": {"count": 1, "edges": [TAG_PEER]}}
    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data=data)
    tags = node._get_relationship_many("tags")

    tags.add("rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr")

    assert [peer.is_loaded for peer in tags.peers] == [True, True]
    assert tags[0].is_loaded is True


@pytest.mark.parametrize("client_type", client_types)
def test_field_objects_built_on_their_own_are_loaded(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data={"id": LOCATION_ID})
    attribute_schema = location_schema.get_attribute(name="description")
    primary_tag_schema = location_schema.get_relationship(name="primary_tag")
    tags_schema = location_schema.get_relationship(name="tags")

    attribute = Attribute(name="description", schema=attribute_schema, data=None)
    related_node: RelatedNode | RelatedNodeSync
    manager: RelationshipManager | RelationshipManagerSync
    if isinstance(node, InfrahubNode):
        related_node = RelatedNode(client=clients.standard, branch="main", schema=primary_tag_schema, data=None)
        manager = RelationshipManager(
            name="tags", client=clients.standard, node=node, branch="main", schema=tags_schema, data=None
        )
    else:
        related_node = RelatedNodeSync(client=clients.sync, branch="main", schema=primary_tag_schema, data=None)
        manager = RelationshipManagerSync(
            name="tags", client=clients.sync, node=node, branch="main", schema=tags_schema, data=None
        )

    assert [attribute.is_loaded, related_node.is_loaded, manager.is_loaded] == [True, True, True]


@pytest.mark.parametrize("client_type", client_types)
def test_fields_that_are_not_loaded_read_as_before(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data={"id": LOCATION_ID})
    description = node._get_attribute("description")
    primary_tag = node._get_relationship_one("primary_tag")
    tags = node._get_relationship_many("tags")
    assert [description.is_loaded, primary_tag.is_loaded, tags.is_loaded] == [False, False, False]

    assert description.value is None
    assert description.value_has_been_mutated is False
    assert [
        primary_tag.id,
        primary_tag.hfid,
        primary_tag.hfid_str,
        primary_tag.display_label,
        primary_tag.typename,
        primary_tag.kind,
    ] == [None, None, None, None, None, None]
    assert primary_tag.initialized is False
    assert primary_tag.is_from_profile is False
    with pytest.raises(ValueError, match="Node must have at least one identifier"):
        _ = primary_tag.peer
    assert [tags.peers, tags.peer_ids, tags.peer_hfids, tags.peer_hfids_str] == [[], [], [], []]
    assert tags.initialized is False
    assert tags.is_from_profile is False
    with pytest.raises(UninitializedError, match="Must call fetch"):
        tags.add(TAG_ID)
    assert node.get_path_value(path="description__value") is None
    assert node.get_path_value(path="primary_tag__name__value") is None


@pytest.mark.parametrize("client_type", client_types)
async def test_fetch_on_a_relationship_that_is_not_loaded_raises_as_before(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    node = build_node(clients=clients, client_type=client_type, schema=location_schema, data={"id": LOCATION_ID})
    primary_tag = node._get_relationship_one("primary_tag")
    assert primary_tag.is_loaded is False

    with pytest.raises(Error, match="Unable to fetch the peer, id and/or typename are not defined"):
        if isinstance(primary_tag, RelatedNode):
            await primary_tag.fetch()
        else:
            primary_tag.fetch()


@pytest.mark.parametrize("client_type", client_types)
def test_hierarchy_fields_that_are_not_loaded_read_as_before(clients: BothClients, client_type: str) -> None:
    schema = hierarchical_location_schema(declares_parent_and_children=False)
    node = build_node(clients=clients, client_type=client_type, schema=schema, data={"id": LOCATION_ID})
    parent = node._hierarchical_data["parent"]
    assert isinstance(parent, (RelatedNode, RelatedNodeSync))
    assert [parent.is_loaded, parent.id, parent.initialized] == [False, None, False]

    readings = []
    for name in ("children", "ancestors", "descendants"):
        manager = node._hierarchical_data[name]
        assert isinstance(manager, (RelationshipManager, RelationshipManagerSync))
        readings.append((manager.is_loaded, manager.peers, manager.initialized))
    assert readings == [(False, [], False), (False, [], False), (False, [], False)]
