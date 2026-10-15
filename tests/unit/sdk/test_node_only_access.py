from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import Error, FieldNotLoadedError, UninitializedError
from infrahub_sdk.graphql import Mutation
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync, UploadResult
from infrahub_sdk.node._only import OnlyMarker  # noqa: PLC2701  # the marker is private to the package
from infrahub_sdk.node.attribute import Attribute
from infrahub_sdk.node.related_node import RelatedNode, RelatedNodeSync
from infrahub_sdk.node.relationship import RelationshipManager, RelationshipManagerSync
from infrahub_sdk.schema import NodeSchema, NodeSchemaAPI, SchemaRootAPI
from tests.helpers import only_data
from tests.helpers.only_data import resolve

if TYPE_CHECKING:
    from pathlib import Path

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
            name="tags", client=clients.standard, node=None, branch="main", schema=tags_schema, data=None
        )
    else:
        related_node = RelatedNodeSync(client=clients.sync, branch="main", schema=primary_tag_schema, data=None)
        manager = RelationshipManagerSync(
            name="tags", client=clients.sync, node=None, branch="main", schema=tags_schema, data=None
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


DEVICE = "InfraDevice"
SITE = "InfraSite"
TAG = "BuiltinTag"
REGION = "LocationRegion"
CONTRACT = "NetworkContract"
CONTRACT_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CONTRACT_CONTENT = b"contract content"
CONTRACT_CHECKSUM = hashlib.sha1(CONTRACT_CONTENT, usedforsecurity=False).hexdigest()


def reference(id: str, typename: str, label: str, **fields: dict[str, Any]) -> dict[str, Any]:
    """A peer as the server returns it, with its display label and an HFID made of the label."""
    return {"node": {"id": id, "hfid": [label], "display_label": label, "__typename": typename, **fields}}


DEVICE_WITH_NAME = only_data.node_data(only_data.DEVICE_ID, DEVICE, name={"value": "dev1"})
DEVICE_WITH_HFID = only_data.DEVICE_WITH_HFID
DEVICE_WITH_EVERY_FIELD = only_data.node_data(
    only_data.DEVICE_ID,
    DEVICE,
    description={"value": "core"},
    site=reference(only_data.SITE_ID, SITE, "Paris", name={"value": "Paris"}, description={"value": None}),
    tags={
        "count": 2,
        "edges": [
            reference(only_data.TAG_ID, "BuiltinTag", "red", name={"value": "red"}),
            reference(only_data.TAG_2_ID, "BuiltinTag", "blue", name={"value": "blue"}),
        ],
    },
)
REGION_WITH_NAME = only_data.node_data(only_data.REGION_ID, REGION, name={"value": "Europe"})
REGION_WITH_PARENT = only_data.node_data(
    only_data.REGION_ID, REGION, parent=only_data.peer(only_data.PARENT_ID, REGION, name={"value": "World"})
)


async def query_one(
    clients: BothClients,
    client_type: str,
    httpx_mock: HTTPXMock,
    kind: str,
    only: list[str],
    edge: dict[str, Any],
    **kwargs: object,
) -> AnyNode:
    """Return the one node that `all(kind, only=...)` builds from a response holding `edge`."""
    only_data.add_page(httpx_mock, kind, [edge])
    nodes = await only_data.query_nodes(clients, client_type, "all", kind=kind, only=only, **kwargs)
    return nodes[0]


@dataclass
class NotFetched:
    kind: str
    field: str
    only: list[str]
    peer_of: str | None = None

    @property
    def pattern(self) -> str:
        if self.peer_of:
            reason = f"the node is a peer of {self.peer_of}, queried with only={self.only!r}."
        else:
            reason = f"the node was queried with only={self.only!r}."
        return re.escape(f"{self.kind}.{self.field} was not fetched: {reason}")

    def check(self, error: FieldNotLoadedError) -> None:
        assert [error.kind, error.field, error.only, error.peer_of] == [self.kind, self.field, self.only, self.peer_of]


async def fetch_then_read_peer_description(related_node: RelatedNode | RelatedNodeSync) -> object:
    await resolve(related_node.fetch())
    return related_node.peer._get_attribute("description").value


def cache_no_peer(_field_object: object) -> None:
    return None


async def fetch_each_peer(manager: RelationshipManager | RelationshipManagerSync) -> None:
    for related_node in manager.peers:
        await resolve(related_node.fetch())


@dataclass
class ReadCase:
    name: str
    field: str
    read: Callable[[Any], Any]
    fetched_value: Any
    pages: tuple[tuple[str, list[dict[str, Any]]], ...] = ()
    # An HFID string needs the peer cached on the relationship, which a fetch sets.
    cache_peers: Callable[[Any], Any] = cache_no_peer


READ_CASES = [
    ReadCase(name="attribute-value", field="description", read=lambda attribute: attribute.value, fetched_value="core"),
    ReadCase(name="related-node-id", field="site", read=lambda rel: rel.id, fetched_value=only_data.SITE_ID),
    ReadCase(name="related-node-hfid", field="site", read=lambda rel: rel.hfid, fetched_value=["Paris"]),
    ReadCase(
        name="related-node-hfid-str",
        field="site",
        read=lambda rel: rel.hfid_str,
        fetched_value="InfraSite__Paris",
        pages=((SITE, [only_data.node_data(only_data.SITE_ID, SITE, name={"value": "Paris"})]),),
        cache_peers=lambda rel: rel.fetch(),
    ),
    ReadCase(
        name="related-node-display-label", field="site", read=lambda rel: rel.display_label, fetched_value="Paris"
    ),
    ReadCase(name="related-node-typename", field="site", read=lambda rel: rel.typename, fetched_value=SITE),
    # The server sends no kind with a reference.
    ReadCase(name="related-node-kind", field="site", read=lambda rel: rel.kind, fetched_value=None),
    ReadCase(name="related-node-peer", field="site", read=lambda rel: rel.peer.id, fetched_value=only_data.SITE_ID),
    ReadCase(name="related-node-get", field="site", read=lambda rel: rel.get().id, fetched_value=only_data.SITE_ID),
    ReadCase(
        name="related-node-fetch",
        field="site",
        read=fetch_then_read_peer_description,
        fetched_value="Main site",
        pages=(
            (
                SITE,
                [
                    only_data.node_data(
                        only_data.SITE_ID, SITE, name={"value": "Paris"}, description={"value": "Main site"}
                    )
                ],
            ),
        ),
    ),
    ReadCase(
        name="manager-peers",
        field="tags",
        read=lambda manager: [peer.id for peer in manager.peers],
        fetched_value=[only_data.TAG_ID, only_data.TAG_2_ID],
    ),
    ReadCase(
        name="manager-peer-ids",
        field="tags",
        read=lambda manager: manager.peer_ids,
        fetched_value=[only_data.TAG_ID, only_data.TAG_2_ID],
    ),
    ReadCase(
        name="manager-peer-hfids",
        field="tags",
        read=lambda manager: manager.peer_hfids,
        fetched_value=[["red"], ["blue"]],
    ),
    ReadCase(
        name="manager-peer-hfids-str",
        field="tags",
        read=lambda manager: manager.peer_hfids_str,
        fetched_value=["BuiltinTag__red", "BuiltinTag__blue"],
        pages=(
            (TAG, [only_data.node_data(only_data.TAG_ID, TAG, name={"value": "red"})]),
            (TAG, [only_data.node_data(only_data.TAG_2_ID, TAG, name={"value": "blue"})]),
        ),
        cache_peers=fetch_each_peer,
    ),
    ReadCase(
        name="manager-indexing", field="tags", read=lambda manager: manager[1].id, fetched_value=only_data.TAG_2_ID
    ),
    ReadCase(
        name="manager-iteration",
        field="tags",
        read=lambda manager: [peer.id for peer in manager],
        fetched_value=[only_data.TAG_ID, only_data.TAG_2_ID],
    ),
    ReadCase(
        name="manager-is-from-profile", field="tags", read=lambda manager: manager.is_from_profile, fetched_value=False
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in READ_CASES])
async def test_read_of_a_field_not_fetched_raises(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: ReadCase
) -> None:
    device = await query_one(only_clients, client_type, httpx_mock, kind=DEVICE, only=["name"], edge=DEVICE_WITH_NAME)
    field_object = getattr(device, case.field)
    expected = NotFetched(kind=DEVICE, field=case.field, only=["name"])
    assert field_object.is_loaded is False

    with pytest.raises(FieldNotLoadedError, match=expected.pattern) as error:
        await resolve(case.read(field_object))

    expected.check(error.value)


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in READ_CASES])
async def test_read_of_a_fetched_field_returns_its_value(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: ReadCase
) -> None:
    device = await query_one(
        only_clients,
        client_type,
        httpx_mock,
        kind=DEVICE,
        only=["description", "site", "tags"],
        edge=DEVICE_WITH_EVERY_FIELD,
        prefetch_relationships=True,
    )
    for kind, edges in case.pages:
        only_data.add_page(httpx_mock, kind, edges)
    field_object = getattr(device, case.field)
    assert field_object.is_loaded is True
    await resolve(case.cache_peers(field_object))

    assert await resolve(case.read(field_object)) == case.fetched_value


ATTRIBUTE_READS_THAT_NEVER_RAISE = (
    "is_loaded",
    "name",
    "id",
    "is_default",
    "is_from_profile",
    "is_inherited",
    "updated_at",
    "is_protected",
    "source",
    "owner",
    "updated_by",
)
RELATED_NODE_READS_THAT_NEVER_RAISE = (
    "is_loaded",
    "initialized",
    "is_resource_pool",
    "is_from_profile",
    "name",
    "is_protected",
    "updated_at",
    "source",
    "owner",
)
MANAGER_READS_THAT_NEVER_RAISE = ("is_loaded", "initialized", "has_update", "name")


@pytest.mark.parametrize("client_type", client_types)
async def test_reads_that_never_raise_on_fields_not_fetched(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    device = await query_one(only_clients, client_type, httpx_mock, kind=DEVICE, only=["name"], edge=DEVICE_WITH_NAME)

    site_relationship = device._get_relationship_one("site")
    tags_relationship = device._get_relationship_many("tags")

    description = {
        name: getattr(device._get_attribute("description"), name) for name in ATTRIBUTE_READS_THAT_NEVER_RAISE
    }
    site = {name: getattr(site_relationship, name) for name in RELATED_NODE_READS_THAT_NEVER_RAISE}
    tags = {name: getattr(tags_relationship, name) for name in MANAGER_READS_THAT_NEVER_RAISE}

    assert description == {
        "is_loaded": False,
        "name": "description",
        "id": None,
        "is_default": None,
        "is_from_profile": None,
        "is_inherited": None,
        "updated_at": None,
        "is_protected": None,
        "source": None,
        "owner": None,
        "updated_by": None,
    }
    assert site == {
        "is_loaded": False,
        "initialized": False,
        "is_resource_pool": False,
        "is_from_profile": False,
        "name": "site",
        "is_protected": None,
        "updated_at": None,
        "source": None,
        "owner": None,
    }
    assert tags == {"is_loaded": False, "initialized": False, "has_update": False, "name": "tags"}
    assert [site_relationship.schema.name, tags_relationship.schema.name] == ["site", "tags"]


@dataclass
class EditCase:
    name: str
    edit: Callable[[Any], None]


EDIT_CASES = [
    EditCase(name="add", edit=lambda manager: manager.add(only_data.TAG_ID)),
    EditCase(name="extend", edit=lambda manager: manager.extend([only_data.TAG_ID])),
    EditCase(name="remove", edit=lambda manager: manager.remove(only_data.TAG_ID)),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in EDIT_CASES])
async def test_edit_of_a_relationship_not_fetched_raises_as_before(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: EditCase
) -> None:
    device = await query_one(only_clients, client_type, httpx_mock, kind=DEVICE, only=["name"], edge=DEVICE_WITH_NAME)
    tags = device._get_relationship_many("tags")
    assert tags.is_loaded is False

    with pytest.raises(UninitializedError, match=re.escape("Must call fetch() on RelationshipManager before editing")):
        case.edit(tags)

    assert [tags.is_loaded, tags.has_update] == [False, False]


@dataclass
class HierarchyReadCase:
    name: str
    read: Callable[[Any], Any]


HIERARCHY_READ_CASES = [
    HierarchyReadCase(name="parent", read=lambda rel: rel.id),
    HierarchyReadCase(name="children", read=lambda manager: manager.peers),
    HierarchyReadCase(name="ancestors", read=lambda manager: manager.peers),
    HierarchyReadCase(name="descendants", read=lambda manager: manager.peers),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in HIERARCHY_READ_CASES])
async def test_read_of_a_hierarchy_field_not_fetched_raises(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: HierarchyReadCase
) -> None:
    region = await query_one(only_clients, client_type, httpx_mock, kind=REGION, only=["name"], edge=REGION_WITH_NAME)
    expected = NotFetched(kind=REGION, field=case.name, only=["name"])

    for field_object in (getattr(region, case.name), region._hierarchical_data[case.name]):
        assert field_object.is_loaded is False
        with pytest.raises(FieldNotLoadedError, match=expected.pattern) as error:
            case.read(field_object)
        expected.check(error.value)


@pytest.mark.parametrize("client_type", client_types)
async def test_read_of_a_field_not_fetched_names_the_kind_of_the_node(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    edge = only_data.node_data(only_data.DOG_ID, "TestingDog", name={"value": "Rex"})
    dog = await query_one(only_clients, client_type, httpx_mock, kind="TestingAnimal", only=["name"], edge=edge)
    expected = NotFetched(kind="TestingDog", field="owner", only=["name"])

    with pytest.raises(FieldNotLoadedError, match=expected.pattern) as error:
        _ = dog._get_relationship_one("owner").id

    expected.check(error.value)


@dataclass
class PeerReadCase:
    name: str
    kind: str
    only: list[str]
    edge: dict[str, Any]
    peer_id: str
    peer_kind: str
    peer_name: str
    field: str
    read: Callable[[Any], Any]
    peer_of: str
    prefetch_relationships: bool = False


PEER_READ_CASES = [
    PeerReadCase(
        name="peer-for-the-hfid-attribute",
        kind=DEVICE,
        only=["hfid"],
        edge=DEVICE_WITH_HFID,
        peer_id=only_data.SITE_ID,
        peer_kind=SITE,
        peer_name="Paris",
        field="description",
        read=lambda attribute: attribute.value,
        peer_of="InfraDevice.site",
    ),
    PeerReadCase(
        name="prefetched-parent-cardinality-one",
        kind=REGION,
        only=["parent"],
        edge=REGION_WITH_PARENT,
        peer_id=only_data.PARENT_ID,
        peer_kind=REGION,
        peer_name="World",
        field="parent",
        read=lambda rel: rel.id,
        peer_of="LocationRegion.parent",
        prefetch_relationships=True,
    ),
    PeerReadCase(
        name="prefetched-parent-cardinality-many",
        kind=REGION,
        only=["parent"],
        edge=REGION_WITH_PARENT,
        peer_id=only_data.PARENT_ID,
        peer_kind=REGION,
        peer_name="World",
        field="children",
        read=lambda manager: manager.peer_ids,
        peer_of="LocationRegion.parent",
        prefetch_relationships=True,
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in PEER_READ_CASES])
async def test_read_of_a_field_not_fetched_on_a_peer_raises(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: PeerReadCase
) -> None:
    await query_one(
        only_clients,
        client_type,
        httpx_mock,
        kind=case.kind,
        only=case.only,
        edge=case.edge,
        prefetch_relationships=case.prefetch_relationships,
    )
    peer = only_data.client_of(only_clients, client_type).store.get(key=case.peer_id, kind=case.peer_kind)
    assert isinstance(peer, (InfrahubNode, InfrahubNodeSync))
    field_object = getattr(peer, case.field)
    expected = NotFetched(kind=case.peer_kind, field=case.field, only=case.only, peer_of=case.peer_of)
    peer_name = peer._get_attribute("name")
    assert [peer_name.is_loaded, peer_name.value, field_object.is_loaded] == [True, case.peer_name, False]

    with pytest.raises(FieldNotLoadedError, match=expected.pattern) as error:
        case.read(field_object)

    expected.check(error.value)


@dataclass
class NodeReadCase:
    name: str
    only: list[str]
    edge: dict[str, Any]
    read: Callable[[Any], Any]
    expected_value: Any = None
    not_fetched: NotFetched | None = None


NODE_READ_CASES = [
    NodeReadCase(
        name="path-to-an-attribute-not-fetched",
        only=["hfid"],
        edge=DEVICE_WITH_HFID,
        read=lambda node: node.get_path_value(path="description__value"),
        not_fetched=NotFetched(kind=DEVICE, field="description", only=["hfid"]),
    ),
    NodeReadCase(
        name="path-through-a-relationship-not-fetched",
        only=["name"],
        edge=DEVICE_WITH_NAME,
        read=lambda node: node.get_path_value(path="site__name__value"),
        not_fetched=NotFetched(kind=DEVICE, field="site", only=["name"]),
    ),
    NodeReadCase(
        name="path-to-a-peer-attribute-not-fetched",
        only=["hfid"],
        edge=DEVICE_WITH_HFID,
        read=lambda node: node.get_path_value(path="site__description__value"),
        not_fetched=NotFetched(kind=SITE, field="description", only=["hfid"], peer_of="InfraDevice.site"),
    ),
    NodeReadCase(
        name="flat-value-of-an-attribute-not-fetched",
        only=["hfid"],
        edge=DEVICE_WITH_HFID,
        read=lambda node: node.get_flat_value(key="description__value"),
        not_fetched=NotFetched(kind=DEVICE, field="description", only=["hfid"]),
    ),
    NodeReadCase(
        name="flat-value-through-a-relationship-not-fetched",
        only=["name"],
        edge=DEVICE_WITH_NAME,
        read=lambda node: node.get_flat_value(key="site__name__value"),
        not_fetched=NotFetched(kind=DEVICE, field="site", only=["name"]),
    ),
    NodeReadCase(
        name="path-to-a-fetched-attribute",
        only=["hfid"],
        edge=DEVICE_WITH_HFID,
        read=lambda node: node.get_path_value(path="name__value"),
        expected_value="dev1",
    ),
    NodeReadCase(
        name="path-to-a-fetched-peer-attribute",
        only=["hfid"],
        edge=DEVICE_WITH_HFID,
        read=lambda node: node.get_path_value(path="site__name__value"),
        expected_value="Paris",
    ),
    NodeReadCase(
        name="flat-value-of-a-fetched-attribute",
        only=["hfid"],
        edge=DEVICE_WITH_HFID,
        read=lambda node: node.get_flat_value(key="name__value"),
        expected_value="dev1",
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in NODE_READ_CASES])
async def test_node_reads_raise_only_for_fields_not_fetched(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: NodeReadCase
) -> None:
    device = await query_one(only_clients, client_type, httpx_mock, kind=DEVICE, only=case.only, edge=case.edge)

    if case.not_fetched is None:
        assert await resolve(case.read(device)) == case.expected_value
        return

    with pytest.raises(FieldNotLoadedError, match=case.not_fetched.pattern) as error:
        await resolve(case.read(device))
    case.not_fetched.check(error.value)


@dataclass
class FileCase:
    name: str
    call: Callable[[Any, Path], Any]
    fetched_value: Any


FILE_CASES = [
    FileCase(
        name="matches-local-checksum",
        call=lambda node, _dest: node.matches_local_checksum(source=CONTRACT_CONTENT),
        fetched_value=True,
    ),
    FileCase(
        name="download-file-skip-if-unchanged",
        call=lambda node, dest: node.download_file(dest=dest, skip_if_unchanged=True),
        fetched_value=0,
    ),
    FileCase(
        name="upload-if-changed",
        call=lambda node, _dest: node.upload_if_changed(source=CONTRACT_CONTENT, name="contract.pdf"),
        fetched_value=UploadResult(was_uploaded=False, checksum=CONTRACT_CHECKSUM),
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in FILE_CASES])
async def test_file_checks_raise_when_the_checksum_was_not_fetched(
    only_clients: BothClients, httpx_mock: HTTPXMock, tmp_path: Path, client_type: str, case: FileCase
) -> None:
    dest = tmp_path / "contract.pdf"
    dest.write_bytes(CONTRACT_CONTENT)
    edge = only_data.node_data(CONTRACT_ID, CONTRACT, file_name={"value": "contract.pdf"})
    contract = await query_one(only_clients, client_type, httpx_mock, kind=CONTRACT, only=["file_name"], edge=edge)
    expected = NotFetched(kind=CONTRACT, field="checksum", only=["file_name"])

    with pytest.raises(FieldNotLoadedError, match=expected.pattern) as error:
        await resolve(case.call(contract, dest))

    expected.check(error.value)


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in FILE_CASES])
async def test_file_checks_compare_with_a_fetched_checksum(
    only_clients: BothClients, httpx_mock: HTTPXMock, tmp_path: Path, client_type: str, case: FileCase
) -> None:
    dest = tmp_path / "contract.pdf"
    dest.write_bytes(CONTRACT_CONTENT)
    edge = only_data.node_data(CONTRACT_ID, CONTRACT, checksum={"value": CONTRACT_CHECKSUM})
    contract = await query_one(only_clients, client_type, httpx_mock, kind=CONTRACT, only=["checksum"], edge=edge)

    assert await resolve(case.call(contract, dest)) == case.fetched_value


MUTATION_RESULT_QUERY: dict[str, Any] = {"ok": None, "object": {"id": None}}


def add_mutation(httpx_mock: HTTPXMock, mutation: str, id: str) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {mutation: {"ok": True, "object": {"id": id}}}},
        match_headers={"X-Infrahub-Tracker": tracker_of(mutation)},
    )


def tracker_of(mutation: str) -> str:
    for action in ("Create", "Update", "Upsert"):
        if mutation.endswith(action):
            return f"mutation-{mutation.removesuffix(action).lower()}-{action.lower()}"
    raise ValueError(f"Unexpected mutation {mutation}")


def sent_mutation(httpx_mock: HTTPXMock, mutation: str) -> str:
    request = httpx_mock.get_request(match_headers={"X-Infrahub-Tracker": tracker_of(mutation)})
    assert request is not None
    return json.loads(request.content)["query"]


@dataclass
class UpdateCase:
    name: str
    kind: str
    node_id: str
    edge: dict[str, Any]
    save: Callable[[Any], Any]


UPDATE_CASES = [
    UpdateCase(
        name="save-device",
        kind=DEVICE,
        node_id=only_data.DEVICE_ID,
        edge=DEVICE_WITH_NAME,
        save=lambda node: node.save(),
    ),
    UpdateCase(
        name="update-device",
        kind=DEVICE,
        node_id=only_data.DEVICE_ID,
        edge=DEVICE_WITH_NAME,
        save=lambda node: node.update(),
    ),
    UpdateCase(
        name="save-hierarchical-node",
        kind=REGION,
        node_id=only_data.REGION_ID,
        edge=REGION_WITH_NAME,
        save=lambda node: node.save(),
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in UPDATE_CASES])
async def test_update_of_a_node_from_only_sends_its_id_and_changed_fields(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: UpdateCase
) -> None:
    node = await query_one(only_clients, client_type, httpx_mock, kind=case.kind, only=["name"], edge=case.edge)
    add_mutation(httpx_mock, f"{case.kind}Update", case.node_id)

    node._get_attribute("name").value = "renamed"
    await resolve(case.save(node))

    expected = Mutation(
        mutation=f"{case.kind}Update",
        input_data={"data": {"name": {"value": "renamed"}, "id": case.node_id}},
        query=MUTATION_RESULT_QUERY,
    )
    assert sent_mutation(httpx_mock, f"{case.kind}Update") == expected.render()
    assert [node.id, node._get_attribute("name").value] == [case.node_id, "renamed"]


@dataclass
class CreateCase:
    name: str
    create: Callable[[Any], Any]
    mutation: str


CREATE_CASES = [
    CreateCase(name="save-with-upsert", create=lambda node: node.save(allow_upsert=True), mutation="InfraDeviceUpsert"),
    CreateCase(
        name="create-with-upsert", create=lambda node: node.create(allow_upsert=True), mutation="InfraDeviceUpsert"
    ),
    CreateCase(name="create", create=lambda node: node.create(), mutation="InfraDeviceCreate"),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in CREATE_CASES])
async def test_create_of_a_node_from_only_sends_its_fetched_fields(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: CreateCase
) -> None:
    device = await query_one(only_clients, client_type, httpx_mock, kind=DEVICE, only=["name"], edge=DEVICE_WITH_NAME)
    add_mutation(httpx_mock, case.mutation, only_data.DEVICE_ID)

    await resolve(case.create(device))

    expected = Mutation(
        mutation=case.mutation,
        input_data={"data": {"name": {"value": "dev1"}, "id": only_data.DEVICE_ID}},
        query=MUTATION_RESULT_QUERY,
    )
    assert sent_mutation(httpx_mock, case.mutation) == expected.render()


@dataclass
class HfidReadCase:
    name: str
    only: list[str]
    edge: dict[str, Any]
    expected: list[Any]


HFID_READ_CASES = [
    HfidReadCase(
        name="hfid-fields-not-fetched", only=["name"], edge=DEVICE_WITH_NAME, expected=[None, None, None, None]
    ),
    HfidReadCase(
        name="hfid-fields-fetched",
        only=["hfid"],
        edge=DEVICE_WITH_HFID,
        expected=[["dev1", "Paris"], "InfraDevice__dev1__Paris", ["dev1", "Paris"], "dev1__Paris"],
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in HFID_READ_CASES])
async def test_hfid_of_a_node_from_only_does_not_raise(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: HfidReadCase
) -> None:
    device = await query_one(only_clients, client_type, httpx_mock, kind=DEVICE, only=case.only, edge=case.edge)

    hfid_reads = [
        device.hfid,
        device.hfid_str,
        device.get_human_friendly_id(),
        device.get_human_friendly_id_as_string(),
    ]

    assert hfid_reads == case.expected


HFID_SITE_SCHEMA = NodeSchema(
    name="Site",
    namespace="Infra",
    human_friendly_id=["name__value"],
    attributes=[{"name": "name", "kind": "Text"}],
).convert_api()
HFID_DEVICE_DATA = {
    "id": only_data.DEVICE_ID,
    "name": {"value": "dev1", "is_protected": True},
    "site": {"node": {"id": only_data.SITE_ID, "hfid": ["Paris"], "display_label": "Paris", "__typename": SITE}},
}
SITE_WITH_NAME = {"id": only_data.SITE_ID, "name": {"value": "Paris", "is_protected": True}}


def device_schema_with_hfid(path: str) -> NodeSchemaAPI:
    return NodeSchema(
        name="Device",
        namespace="Infra",
        human_friendly_id=[path],
        attributes=[{"name": "name", "kind": "Text"}, {"name": "description", "kind": "Text", "optional": True}],
        relationships=[{"name": "site", "peer": SITE, "cardinality": "one", "optional": True}],
    ).convert_api()


@dataclass
class DefaultHfidCase:
    name: str
    path: str
    path_value: Callable[[Any], Any]
    site_data: dict[str, Any] = field(default_factory=lambda: SITE_WITH_NAME)


DEFAULT_HFID_CASES = [
    DefaultHfidCase(name="relationship", path="site", path_value=lambda _device: ["Paris"]),
    DefaultHfidCase(
        name="relationship-to-a-peer-without-hfid",
        path="site",
        path_value=lambda _device: only_data.SITE_ID,
        site_data={"id": only_data.SITE_ID},
    ),
    DefaultHfidCase(name="relationship-attribute", path="site__name", path_value=lambda device: device.site.peer.name),
    DefaultHfidCase(name="relationship-attribute-value", path="site__name__value", path_value=lambda _device: "Paris"),
    DefaultHfidCase(
        name="relationship-attribute-property", path="site__name__is_protected", path_value=lambda _device: True
    ),
    DefaultHfidCase(name="attribute", path="name", path_value=lambda device: device._get_attribute("name")),
    DefaultHfidCase(name="attribute-value", path="name__value", path_value=lambda _device: "dev1"),
    DefaultHfidCase(name="attribute-property", path="name__is_protected", path_value=lambda _device: True),
    DefaultHfidCase(name="attribute-not-in-data", path="description__value", path_value=lambda _device: None),
    DefaultHfidCase(
        name="attribute-not-in-data-without-property",
        path="description",
        path_value=lambda device: device._get_attribute("description"),
    ),
    DefaultHfidCase(name="unknown-first-part", path="rack__name__value", path_value=lambda _device: None),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in DEFAULT_HFID_CASES])
def test_hfid_of_a_default_node_is_built_from_its_path_values(
    clients: BothClients, client_type: str, case: DefaultHfidCase
) -> None:
    site = build_node(clients=clients, client_type=client_type, schema=HFID_SITE_SCHEMA, data=case.site_data)
    if isinstance(site, InfrahubNode):
        clients.standard.store.set(node=site)
    else:
        clients.sync.store.set(node=site)
    device = build_node(
        clients=clients, client_type=client_type, schema=device_schema_with_hfid(case.path), data=HFID_DEVICE_DATA
    )

    path_value = device.get_path_value(path=case.path)
    expected_hfid = None if path_value is None else [str(path_value)]

    assert path_value == case.path_value(device)
    assert [device.hfid, device.get_human_friendly_id()] == [expected_hfid, expected_hfid]


@dataclass
class OnlyHfidCase:
    name: str
    path: str
    expected_hfid: Callable[[Any], list[str] | None]
    site_data: dict[str, Any] = field(default_factory=lambda: SITE_WITH_NAME)


ONLY_HFID_CASES = [
    OnlyHfidCase(name="relationship", path="site", expected_hfid=lambda _device: [str(["Paris"])]),
    OnlyHfidCase(
        name="relationship-to-a-peer-without-hfid",
        path="site",
        expected_hfid=lambda _device: [only_data.SITE_ID],
        site_data={"id": only_data.SITE_ID},
    ),
    OnlyHfidCase(
        name="relationship-attribute",
        path="site__name",
        expected_hfid=lambda device: [str(device.site.peer.name)],
    ),
    OnlyHfidCase(
        name="relationship-attribute-value", path="site__name__value", expected_hfid=lambda _device: ["Paris"]
    ),
    OnlyHfidCase(
        name="relationship-attribute-property", path="site__name__is_protected", expected_hfid=lambda _device: ["True"]
    ),
    OnlyHfidCase(name="attribute", path="name", expected_hfid=lambda device: [str(device._get_attribute("name"))]),
    OnlyHfidCase(name="attribute-value", path="name__value", expected_hfid=lambda _device: ["dev1"]),
    OnlyHfidCase(name="attribute-property", path="name__is_protected", expected_hfid=lambda _device: ["True"]),
    OnlyHfidCase(name="attribute-not-fetched", path="description__value", expected_hfid=lambda _device: None),
    OnlyHfidCase(name="attribute-not-fetched-without-property", path="description", expected_hfid=lambda _device: None),
    OnlyHfidCase(name="unknown-first-part", path="rack__name__value", expected_hfid=lambda _device: None),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in ONLY_HFID_CASES])
def test_hfid_of_a_node_from_only_is_built_from_the_fields_it_fetched(
    clients: BothClients, client_type: str, case: OnlyHfidCase
) -> None:
    site = build_node(clients=clients, client_type=client_type, schema=HFID_SITE_SCHEMA, data=case.site_data)
    if isinstance(site, InfrahubNode):
        clients.standard.store.set(node=site)
    else:
        clients.sync.store.set(node=site)
    device = build_node(
        clients=clients, client_type=client_type, schema=device_schema_with_hfid(case.path), data=HFID_DEVICE_DATA
    )
    device._only_marker = OnlyMarker(only=("name", "site"))

    expected_hfid = case.expected_hfid(device)

    assert [device.hfid, device.get_human_friendly_id()] == [expected_hfid, expected_hfid]


@pytest.mark.parametrize("client_type", client_types)
async def test_hfid_of_a_default_node_skips_a_stored_peer_field_that_only_did_not_fetch(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    site_without_name = only_data.node_data(only_data.SITE_ID, SITE, description={"value": "hq"})
    await query_one(only_clients, client_type, httpx_mock, kind=SITE, only=["description"], edge=site_without_name)
    device = build_node(
        clients=only_clients,
        client_type=client_type,
        schema=device_schema_with_hfid("site__name__value"),
        data=HFID_DEVICE_DATA,
    )

    assert [device.hfid, device.get_human_friendly_id()] == [None, None]


@pytest.mark.parametrize("client_type", client_types)
async def test_store_accepts_a_node_from_only(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    client = only_data.client_of(only_clients, client_type)
    device = await query_one(
        only_clients, client_type, httpx_mock, kind=DEVICE, only=["name"], edge=DEVICE_WITH_NAME, populate_store=False
    )
    assert client.store.count() == 0

    if isinstance(device, InfrahubNode):
        only_clients.standard.store.set(node=device)
    else:
        only_clients.sync.store.set(node=device)

    assert client.store.get(key=only_data.DEVICE_ID, kind=DEVICE) is device


@pytest.mark.parametrize("client_type", client_types)
async def test_mutation_result_on_a_node_from_only(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    device = await query_one(only_clients, client_type, httpx_mock, kind=DEVICE, only=["name"], edge=DEVICE_WITH_NAME)
    response = {
        "InfraDeviceUpdate": {"ok": True, "object": {"id": only_data.DEVICE_ID, "description": {"value": "edge"}}}
    }

    await resolve(device._process_mutation_result(mutation_name="InfraDeviceUpdate", response=response))

    assert [device.id, device._get_attribute("description").is_loaded] == [only_data.DEVICE_ID, False]


@pytest.mark.parametrize("client_type", client_types)
async def test_repr_of_a_node_from_only(only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str) -> None:
    device = await query_one(only_clients, client_type, httpx_mock, kind=DEVICE, only=["name"], edge=DEVICE_WITH_NAME)

    assert [repr(device), str(device)] == [f"InfraDevice ({only_data.DEVICE_ID}) "] * 2
