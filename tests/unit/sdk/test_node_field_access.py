"""Tests for reading node attributes and relationships whose value the SDK may not know."""

from __future__ import annotations

import inspect
import json
import re
import warnings
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from operator import attrgetter
from typing import TYPE_CHECKING, Any

import pytest
from graphql import FieldNode, OperationDefinitionNode, parse, value_from_ast_untyped

from infrahub_sdk.exceptions import (
    Error,
    FieldNotLoadedError,
    FieldNotLoadedWarning,
    NodeNotFoundError,
    UninitializedError,
)
from infrahub_sdk.node import (
    Attribute,
    InfrahubNode,
    InfrahubNodeSync,
    RelationshipManager,
    RelationshipManagerSync,
)
from infrahub_sdk.node.selection import Selection
from infrahub_sdk.schema import NodeSchema

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator, Mapping
    from contextlib import AbstractContextManager

    import httpx
    from pytest_httpx import HTTPXMock

    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from infrahub_sdk.schema import MainSchemaTypesAPI, NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

LOCATION_ID = "llllllll-llll-llll-llll-llllllllllll"
PRIMARY_TAG_ID = "rrrrrrrr-rrrr-rrrr-rrrr-rrrrrrrrrrrr"
TAG_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
RACK_ID = "kkkkkkkk-kkkk-kkkk-kkkk-kkkkkkkkkkkk"
ROOM_ID = "oooooooo-oooo-oooo-oooo-oooooooooooo"
BUILDING_ID = "pppppppp-pppp-pppp-pppp-pppppppppppp"

UNKNOWN_ORIGIN_MESSAGE = (
    "{kind}.{field} is not known to the SDK (origin unknown). "
    "Fetch the node with a selection that includes it before reading it."
)
WARNING_SUFFIX = " This will raise FieldNotLoadedError in infrahub-sdk 2.0."


def location_payload(omit: Collection[str] = (), overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a GraphQL edge for ``location_schema`` carrying every field except the keys in ``omit``.

    ``overrides`` replaces the value of existing keys.

    Raises:
        ValueError: If ``omit`` or ``overrides`` names a key the payload does not carry.

    """
    node: dict[str, Any] = {
        "__typename": "BuiltinLocation",
        "id": LOCATION_ID,
        "hfid": None,
        "display_label": "dfw1",
        "name": {"value": "DFW"},
        "description": {"value": "Dallas data center"},
        "type": {"value": "SITE"},
        "primary_tag": {
            "node": {"id": PRIMARY_TAG_ID, "hfid": ["red"], "display_label": "red", "__typename": "BuiltinTag"},
        },
        "tags": {
            "count": 1,
            "edges": [{"node": {"id": TAG_ID, "hfid": ["blue"], "display_label": "blue", "__typename": "BuiltinTag"}}],
        },
        "member_of_groups": {"count": 0, "edges": []},
    }
    overrides = overrides or {}
    # Fail loudly on a typo so a test never runs against a payload it did not mean to build.
    unknown = (set(omit) | set(overrides)) - node.keys()
    if unknown:
        raise ValueError(f"Cannot omit or override keys that the location payload does not carry: {sorted(unknown)}")
    node.update(overrides)
    return {"node": {key: value for key, value in node.items() if key not in omit}}


def new_location_data() -> dict[str, Any]:
    """Return the data of a location that was never saved, so it has no ``id``."""
    return {"name": {"value": "DFW"}, "type": {"value": "SITE"}}


def make_node(
    client_type: str, clients: BothClients, schema: MainSchemaTypesAPI, data: dict[str, Any] | None
) -> InfrahubNode | InfrahubNodeSync:
    if client_type == "standard":
        return InfrahubNode(client=clients.standard, schema=schema, data=data)
    return InfrahubNodeSync(client=clients.sync, schema=schema, data=data)


def client_for(client_type: str, clients: BothClients) -> InfrahubClient | InfrahubClientSync:
    return clients.standard if client_type == "standard" else clients.sync


def store_node(clients: BothClients, node: InfrahubNode | InfrahubNodeSync) -> None:
    if isinstance(node, InfrahubNode):
        clients.standard.store.set(node=node)
    else:
        clients.sync.store.set(node=node)


def attribute_of(node: InfrahubNode | InfrahubNodeSync, name: str) -> Attribute:
    attribute = getattr(node, name)
    assert isinstance(attribute, Attribute)
    return attribute


def tags_of(node: InfrahubNode | InfrahubNodeSync) -> RelationshipManager | RelationshipManagerSync:
    manager = node.tags
    assert isinstance(manager, (RelationshipManager, RelationshipManagerSync))
    return manager


async def save_node(node: InfrahubNode | InfrahubNodeSync, allow_upsert: bool = False) -> None:
    if isinstance(node, InfrahubNode):
        await node.save(allow_upsert=allow_upsert)
    else:
        node.save(allow_upsert=allow_upsert)


def unknown_origin_warning(kind: str, field: str) -> str:
    """Return the exact 1.x warning text for a read of ``<kind>.<field>`` on a node whose origin is unknown."""
    return UNKNOWN_ORIGIN_MESSAGE.format(kind=kind, field=field) + WARNING_SUFFIX


def exactly(text: str) -> str:
    """Return a ``match=`` pattern that only accepts ``text`` itself."""
    return f"^{re.escape(text)}$"


@contextmanager
def no_field_warning() -> Iterator[None]:
    """Fail if the block emits a FieldNotLoadedWarning, whatever the active warning filters."""
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        yield
    assert [str(item.message) for item in record if issubclass(item.category, FieldNotLoadedWarning)] == []


@pytest.fixture
def strict_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every read of a field the SDK does not know raise FieldNotLoadedError, as infrahub-sdk 2.0 will."""
    monkeypatch.setattr("infrahub_sdk.node.field_access._STRICT_FIELD_ACCESS", True)


@pytest.fixture(params=[pytest.param(False, id="warn"), pytest.param(True, id="strict")])
def strict_switch(request: pytest.FixtureRequest) -> bool:
    """Run the test with the strict switch off, then on, and return whether it is on."""
    strict: bool = request.param
    if strict:
        request.getfixturevalue("strict_access")
    return strict


@contextmanager
def reports_unloaded_read(kind: str, field: str, strict: bool) -> Iterator[None]:
    """Expect the block to report one read of ``<kind>.<field>`` on a node whose origin is unknown.

    The report is the 1.x warning or, when ``strict``, FieldNotLoadedError with the same text minus the 1.x
    suffix. The error ends the block at the read, so the rest of the block only runs without ``strict``.
    """
    warning = unknown_origin_warning(kind, field)
    if strict:
        message = warning.removesuffix(WARNING_SUFFIX)
        with pytest.raises(FieldNotLoadedError, match=exactly(message)) as exc_info:
            yield
        assert (exc_info.value.kind, exc_info.value.field, exc_info.value.selection) == (kind, field, None)
    else:
        with pytest.warns(FieldNotLoadedWarning, match=exactly(warning)) as record:
            yield
        assert [str(item.message) for item in record] == [warning]


def expect_read_report(reported: bool, kind: str, field: str, strict: bool) -> AbstractContextManager[None]:
    """Return :func:`reports_unloaded_read` for a row that reports the read, else :func:`no_field_warning`."""
    return reports_unloaded_read(kind, field, strict) if reported else no_field_warning()


def mutation_input(request: httpx.Request) -> dict[str, Any]:
    """Return the ``data`` argument of the mutation sent in ``request``, as plain Python values."""
    document = parse(json.loads(request.content)["query"])
    operation = document.definitions[0]
    assert isinstance(operation, OperationDefinitionNode)
    mutation = operation.selection_set.selections[0]
    assert isinstance(mutation, FieldNode)
    data_argument = next(argument for argument in mutation.arguments if argument.name.value == "data")
    data = value_from_ast_untyped(data_argument.value)
    assert isinstance(data, dict)
    return data


@pytest.fixture
def hierarchical_schema() -> NodeSchemaAPI:
    """Schema for a hierarchical location node with hierarchy support."""
    data: dict[str, Any] = {
        "name": "Location",
        "namespace": "Infra",
        "default_filter": "name__value",
        "attributes": [
            {"name": "name", "kind": "Text", "unique": True},
            {"name": "description", "kind": "Text", "optional": True},
        ],
        "relationships": [
            {
                "name": "parent",
                "peer": "InfraLocation",
                "optional": True,
                "cardinality": "one",
                "kind": "Hierarchy",
            },
            {
                "name": "children",
                "peer": "InfraLocation",
                "optional": True,
                "cardinality": "many",
                "kind": "Hierarchy",
            },
        ],
    }
    schema_api = NodeSchema(**data).convert_api()
    # The backend sets ``hierarchy``; NodeSchema does not carry it.
    schema_api.hierarchy = "InfraLocation"
    return schema_api


def room_payload(omit: Collection[str] = ()) -> dict[str, Any]:
    """Return a GraphQL edge for ``hierarchical_schema`` without the keys in ``omit``."""
    node: dict[str, Any] = {
        "__typename": "InfraLocation",
        "id": ROOM_ID,
        "hfid": None,
        "display_label": "room-1",
        "name": {"value": "room-1"},
        "description": {"value": None},
        "parent": {
            "node": {"id": BUILDING_ID, "hfid": None, "display_label": "building-1", "__typename": "InfraLocation"}
        },
        "children": {"count": 0, "edges": []},
    }
    return {"node": {key: value for key, value in node.items() if key not in omit}}


@pytest.mark.parametrize("client_type", client_types)
async def test_location_payload_builds_full_and_partial_nodes(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    expected_class = InfrahubNode if client_type == "standard" else InfrahubNodeSync

    full = make_node(client_type, clients, location_schema, location_payload(omit=set()))
    assert type(full) is expected_class
    assert full.id == LOCATION_ID
    assert full.name.value == "DFW"
    assert full.description.value == "Dallas data center"
    assert full.primary_tag.id == PRIMARY_TAG_ID
    assert [peer.id for peer in full.tags.peers] == [TAG_ID]

    partial_payload = location_payload(omit={"description", "primary_tag", "tags"})
    assert sorted(partial_payload["node"]) == [
        "__typename",
        "display_label",
        "hfid",
        "id",
        "member_of_groups",
        "name",
        "type",
    ]
    partial = make_node(client_type, clients, location_schema, partial_payload)
    assert type(partial) is expected_class
    assert partial.id == LOCATION_ID
    assert partial.name.value == "DFW"
    assert partial.tags.initialized is False

    with pytest.raises(ValueError, match=r"\['descripton'\]"):
        location_payload(omit={"descripton"})
    with pytest.raises(ValueError, match=r"\['descripton'\]"):
        location_payload(overrides={"descripton": {"value": None}})


# Attributes


@dataclass
class AttributeReadCase:
    name: str
    data: dict[str, Any]
    expected_value: Any
    expected_loaded: bool
    warns: bool


ATTRIBUTE_READ_CASES = [
    AttributeReadCase(
        name="present-with-value",
        data=location_payload(),
        expected_value="Dallas data center",
        expected_loaded=True,
        warns=False,
    ),
    AttributeReadCase(
        name="present-with-null-value",
        data=location_payload(overrides={"description": {"value": None}}),
        expected_value=None,
        expected_loaded=True,
        warns=False,
    ),
    AttributeReadCase(
        name="absent-on-node-with-id",
        data=location_payload(omit={"description"}),
        expected_value=None,
        expected_loaded=False,
        warns=True,
    ),
    AttributeReadCase(
        name="absent-on-node-without-id",
        data=new_location_data(),
        expected_value=None,
        expected_loaded=True,
        warns=False,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in ATTRIBUTE_READ_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_attribute_value_read(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, case: AttributeReadCase, strict_switch: bool
) -> None:
    node = make_node(client_type, clients, location_schema, deepcopy(case.data))

    with no_field_warning():
        assert node.description.is_loaded is case.expected_loaded

    with expect_read_report(case.warns, "BuiltinLocation", "description", strict_switch):
        assert node.description.value == case.expected_value


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("assign_via", ["attribute-value", "node-attribute"])
@pytest.mark.parametrize("client_type", client_types)
async def test_assigning_absent_attribute_makes_it_known(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, assign_via: str
) -> None:
    node = make_node(client_type, clients, location_schema, location_payload(omit={"description"}))

    with no_field_warning():
        if assign_via == "attribute-value":
            attribute_of(node, "description").value = "Assigned"
        else:
            node.description = "Assigned"

        assert node.description.is_loaded is True
        assert node.description.value == "Assigned"
        assert node.description.value_has_been_mutated is True


@pytest.mark.parametrize("client_type", client_types)
async def test_never_set_attribute_becomes_unknown_once_new_node_is_saved(
    httpx_mock: HTTPXMock, clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, strict_switch: bool
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinLocationCreate": {"ok": True, "object": {"id": "abc"}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-builtinlocation-create"},
    )
    node = make_node(client_type, clients, location_schema, new_location_data())

    with no_field_warning():
        assert node.description.is_loaded is True
        await save_node(node)

        assert node.id == "abc"
        assert node.name.is_loaded is True
        assert node.name.value == "DFW"
        assert node.description.is_loaded is False

    with reports_unloaded_read("BuiltinLocation", "description", strict_switch):
        assert node.description.value is None


@pytest.mark.parametrize("client_type", client_types)
async def test_never_set_relationship_becomes_unknown_once_new_node_is_saved(
    httpx_mock: HTTPXMock, clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, strict_switch: bool
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinLocationCreate": {"ok": True, "object": {"id": "abc"}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-builtinlocation-create"},
    )
    node = make_node(client_type, clients, location_schema, new_location_data())

    with no_field_warning():
        assert node.primary_tag.is_loaded is True
        assert node.primary_tag.id is None
        await save_node(node)

        assert node.id == "abc"
        assert node.primary_tag.is_loaded is False

    with reports_unloaded_read("BuiltinLocation", "primary_tag", strict_switch):
        assert node.primary_tag.id is None


# Cardinality-one relationships


RELATED_NODE_ACCESSORS = ("id", "hfid", "hfid_str", "display_label", "typename", "kind", "initialized")
EMPTY_RELATED_NODE_VALUES: dict[str, Any] = {
    "id": None,
    "hfid": None,
    "hfid_str": None,
    "display_label": None,
    "typename": None,
    "kind": None,
    "initialized": False,
}


@dataclass
class RelatedNodeReadCase:
    name: str
    data: dict[str, Any]
    expected_values: dict[str, Any]
    expected_loaded: bool
    warns: bool


RELATED_NODE_READ_CASES = [
    RelatedNodeReadCase(
        name="present-with-peer",
        data=location_payload(),
        expected_values={
            "id": PRIMARY_TAG_ID,
            "hfid": ["red"],
            "hfid_str": None,
            "display_label": "red",
            "typename": "BuiltinTag",
            "kind": None,
            "initialized": True,
        },
        expected_loaded=True,
        warns=False,
    ),
    RelatedNodeReadCase(
        name="present-with-null-node",
        data=location_payload(overrides={"primary_tag": {"node": None}}),
        expected_values=EMPTY_RELATED_NODE_VALUES,
        expected_loaded=True,
        warns=False,
    ),
    RelatedNodeReadCase(
        name="absent-on-node-with-id",
        data=location_payload(omit={"primary_tag"}),
        expected_values=EMPTY_RELATED_NODE_VALUES,
        expected_loaded=False,
        warns=True,
    ),
    RelatedNodeReadCase(
        name="absent-on-node-without-id",
        data=new_location_data(),
        expected_values=EMPTY_RELATED_NODE_VALUES,
        expected_loaded=True,
        warns=False,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in RELATED_NODE_READ_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_accessor_reads(
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    client_type: str,
    case: RelatedNodeReadCase,
    strict_switch: bool,
) -> None:
    relationship = make_node(client_type, clients, location_schema, deepcopy(case.data)).primary_tag

    with no_field_warning():
        assert relationship.is_loaded is case.expected_loaded

    assert sorted(case.expected_values) == sorted(RELATED_NODE_ACCESSORS)
    for accessor in RELATED_NODE_ACCESSORS:
        with expect_read_report(case.warns, "BuiltinLocation", "primary_tag", strict_switch):
            assert getattr(relationship, accessor) == case.expected_values[accessor]


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("lookup", ["get", "peer"])
@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_peer_lookup_on_present_relationship(
    clients: BothClients, location_schema: NodeSchemaAPI, tag_schema: NodeSchemaAPI, client_type: str, lookup: str
) -> None:
    tag = make_node(
        client_type,
        clients,
        tag_schema,
        {"id": PRIMARY_TAG_ID, "__typename": "BuiltinTag", "display_label": "red", "name": {"value": "red"}},
    )
    store_node(clients, tag)
    relationship = make_node(client_type, clients, location_schema, location_payload()).primary_tag

    with no_field_warning():
        peer = relationship.get() if lookup == "get" else relationship.peer

    assert peer is tag


@dataclass
class PeerLookupCase:
    name: str
    data: dict[str, Any]
    warns: bool


PEER_LOOKUP_CASES = [
    PeerLookupCase(
        name="present-with-null-node", data=location_payload(overrides={"primary_tag": {"node": None}}), warns=False
    ),
    PeerLookupCase(name="absent-on-node-with-id", data=location_payload(omit={"primary_tag"}), warns=True),
    PeerLookupCase(name="absent-on-node-without-id", data=new_location_data(), warns=False),
]


@pytest.mark.parametrize("lookup", ["get", "peer"])
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in PEER_LOOKUP_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_peer_lookup_without_identifier(
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    client_type: str,
    case: PeerLookupCase,
    lookup: str,
    strict_switch: bool,
) -> None:
    relationship = make_node(client_type, clients, location_schema, deepcopy(case.data)).primary_tag

    def read() -> object:
        return relationship.get() if lookup == "get" else relationship.peer

    # When strict, FieldNotLoadedError leaves the ValueError check unmet and propagates to the report check.
    with (
        expect_read_report(case.warns, "BuiltinLocation", "primary_tag", strict_switch),
        pytest.raises(ValueError, match="Node must have at least one identifier"),
    ):
        read()


@dataclass
class RelatedNodeFetchCase:
    name: str
    data: dict[str, Any]
    selection: Selection | None
    message: str


UNKNOWN_PRIMARY_TAG_FETCH_MESSAGE = (
    "Relationship 'primary_tag' was not fetched with its node, so its peer is unknown. "
    "Query the node with 'primary_tag' in its selection first."
)
EMPTY_PRIMARY_TAG_FETCH_MESSAGE = "Unable to fetch the peer, id and/or typename are not defined"

RELATED_NODE_FETCH_CASES = [
    RelatedNodeFetchCase(
        name="unknown-relationship",
        data=location_payload(omit={"primary_tag"}),
        selection=None,
        message=UNKNOWN_PRIMARY_TAG_FETCH_MESSAGE,
    ),
    RelatedNodeFetchCase(
        name="unknown-relationship-of-only-node",
        data=location_payload(omit={"primary_tag"}),
        selection=Selection.from_args(only=["name"]),
        message=UNKNOWN_PRIMARY_TAG_FETCH_MESSAGE,
    ),
    RelatedNodeFetchCase(
        name="known-empty-relationship",
        data=location_payload(overrides={"primary_tag": {"node": None}}),
        selection=None,
        message=EMPTY_PRIMARY_TAG_FETCH_MESSAGE,
    ),
]


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in RELATED_NODE_FETCH_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_fetch_without_a_peer_raises_before_any_read_or_request(
    httpx_mock: HTTPXMock,
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    client_type: str,
    case: RelatedNodeFetchCase,
) -> None:
    node = make_node(client_type, clients, location_schema, deepcopy(case.data))
    node._selection = case.selection
    relationship = node.primary_tag

    with no_field_warning(), pytest.raises(Error, match=exactly(case.message)) as exc_info:
        result = relationship.fetch()
        if inspect.isawaitable(result):
            await result

    assert type(exc_info.value) is Error
    assert httpx_mock.get_requests() == []


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_assigning_absent_related_node_makes_it_known(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    node = make_node(client_type, clients, location_schema, location_payload(omit={"primary_tag"}))

    with no_field_warning():
        node.primary_tag = TAG_ID

        assert node.primary_tag.is_loaded is True
        assert node.primary_tag.id == TAG_ID
        assert node.primary_tag.initialized is True


@dataclass
class ParentReadCase:
    name: str
    omit: frozenset[str]
    expected_id: str | None
    expected_loaded: bool
    warns: bool


PARENT_READ_CASES = [
    ParentReadCase(name="present", omit=frozenset(), expected_id=BUILDING_ID, expected_loaded=True, warns=False),
    ParentReadCase(
        name="absent-on-node-with-id", omit=frozenset({"parent"}), expected_id=None, expected_loaded=False, warns=True
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in PARENT_READ_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_hierarchical_parent_read(
    clients: BothClients,
    hierarchical_schema: NodeSchemaAPI,
    client_type: str,
    case: ParentReadCase,
    strict_switch: bool,
) -> None:
    node = make_node(client_type, clients, hierarchical_schema, room_payload(omit=case.omit))
    # The schema declares ``parent``, and the node also tracks it among its hierarchical fields.
    parents = {"declared": node.parent, "hierarchical": node._hierarchical_data["parent"]}

    for parent in parents.values():
        with no_field_warning():
            assert parent.is_loaded is case.expected_loaded

        with expect_read_report(case.warns, "InfraLocation", "parent", strict_switch):
            assert parent.id == case.expected_id


# Cardinality-many relationships


RELATIONSHIP_MANAGER_READS: dict[str, Callable[[Any], Any]] = {
    "peers": lambda manager: [peer.id for peer in manager.peers],
    "peer_ids": attrgetter("peer_ids"),
    "peer_hfids": attrgetter("peer_hfids"),
    "peer_hfids_str": attrgetter("peer_hfids_str"),
    "is_from_profile": attrgetter("is_from_profile"),
    # Iterating reads ``[0]`` once before it stops.
    "iteration": lambda manager: [peer.id for peer in manager],
}


EMPTY_RELATIONSHIP_MANAGER_VALUES: dict[str, Any] = {
    "peers": [],
    "peer_ids": [],
    "peer_hfids": [],
    "peer_hfids_str": [],
    "is_from_profile": False,
    "iteration": [],
}


@dataclass
class RelationshipManagerReadCase:
    name: str
    data: dict[str, Any]
    expected_values: dict[str, Any]
    expected_loaded: bool
    expected_initialized: bool
    warns: bool


RELATIONSHIP_MANAGER_READ_CASES = [
    RelationshipManagerReadCase(
        name="present-with-peer",
        data=location_payload(),
        expected_values={
            "peers": [TAG_ID],
            "peer_ids": [TAG_ID],
            "peer_hfids": [["blue"]],
            "peer_hfids_str": [],
            "is_from_profile": False,
            "iteration": [TAG_ID],
        },
        expected_loaded=True,
        expected_initialized=True,
        warns=False,
    ),
    RelationshipManagerReadCase(
        name="present-with-no-edges",
        data=location_payload(overrides={"tags": {"count": 0, "edges": []}}),
        expected_values=EMPTY_RELATIONSHIP_MANAGER_VALUES,
        expected_loaded=True,
        expected_initialized=True,
        warns=False,
    ),
    RelationshipManagerReadCase(
        name="absent-on-node-with-id",
        data=location_payload(omit={"tags"}),
        expected_values=EMPTY_RELATIONSHIP_MANAGER_VALUES,
        expected_loaded=False,
        expected_initialized=False,
        warns=True,
    ),
    RelationshipManagerReadCase(
        name="absent-on-node-without-id",
        data=new_location_data(),
        expected_values=EMPTY_RELATIONSHIP_MANAGER_VALUES,
        expected_loaded=True,
        expected_initialized=False,
        warns=False,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in RELATIONSHIP_MANAGER_READ_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_relationship_manager_reads(
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    client_type: str,
    case: RelationshipManagerReadCase,
    strict_switch: bool,
) -> None:
    manager = tags_of(make_node(client_type, clients, location_schema, deepcopy(case.data)))

    with no_field_warning():
        assert manager.is_loaded is case.expected_loaded
        assert manager.initialized is case.expected_initialized

    assert sorted(case.expected_values) == sorted(RELATIONSHIP_MANAGER_READS)
    for accessor, read in RELATIONSHIP_MANAGER_READS.items():
        with expect_read_report(case.warns, "BuiltinLocation", "tags", strict_switch):
            assert read(manager) == case.expected_values[accessor]


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_relationship_manager_index_on_present_relationship(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    manager = tags_of(make_node(client_type, clients, location_schema, location_payload()))

    with no_field_warning():
        assert manager[0].id == TAG_ID


@pytest.mark.parametrize("client_type", client_types)
async def test_relationship_manager_index_on_unknown_relationship(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, strict_switch: bool
) -> None:
    manager = tags_of(make_node(client_type, clients, location_schema, location_payload(omit={"tags"})))

    with (
        reports_unloaded_read("BuiltinLocation", "tags", strict_switch),
        pytest.raises(IndexError, match="list index out of range"),
    ):
        manager[0]


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_relationship_manager_is_known_after_fetch(
    httpx_mock: HTTPXMock,
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    tag_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    client_for(client_type, clients).schema.set_cache(
        {"version": "1.0", "nodes": [location_schema.model_dump(), tag_schema.model_dump()]}
    )
    tag_node = {
        "__typename": "BuiltinTag",
        "id": TAG_ID,
        "hfid": ["blue"],
        "display_label": "blue",
        "name": {"value": "blue"},
        "description": {"value": None},
    }
    httpx_mock.add_response(
        method="POST",
        json={
            "data": {
                "BuiltinLocation": {
                    "count": 1,
                    "edges": [
                        {
                            "node": {
                                "__typename": "BuiltinLocation",
                                "id": LOCATION_ID,
                                "hfid": None,
                                "display_label": "dfw1",
                                "tags": {"count": 1, "edges": [{"node": tag_node}]},
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
        json={"data": {"BuiltinTag": {"count": 1, "edges": [{"node": tag_node}]}}},
        match_headers={"X-Infrahub-Tracker": "query-builtintag-page1"},
    )
    # The peer batch counts the peers first; that query carries no tracker.
    httpx_mock.add_response(method="POST", json={"data": {"BuiltinTag": {"count": 1}}})

    node = make_node(client_type, clients, location_schema, location_payload(omit={"tags"}))

    with no_field_warning():
        assert node.tags.is_loaded is False
        if isinstance(node, InfrahubNode):
            await node._get_relationship_many(name="tags").fetch()
        else:
            node._get_relationship_many(name="tags").fetch()

        assert node.tags.initialized is True
        assert node.tags.is_loaded is True
        assert node.tags.peer_ids == [TAG_ID]


@dataclass
class ManagerEditCase:
    name: str
    edit: Callable[[Any], None]


MANAGER_EDIT_CASES = [
    ManagerEditCase(name="add", edit=lambda manager: manager.add(TAG_ID)),
    ManagerEditCase(name="extend", edit=lambda manager: manager.extend([TAG_ID])),
    ManagerEditCase(name="remove", edit=lambda manager: manager.remove(TAG_ID)),
]


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in MANAGER_EDIT_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_editing_unknown_relationship_manager_still_requires_fetch(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, case: ManagerEditCase
) -> None:
    manager = tags_of(make_node(client_type, clients, location_schema, location_payload(omit={"tags"})))

    with (
        no_field_warning(),
        pytest.raises(UninitializedError, match=r"^Must call fetch\(\) on RelationshipManager before editing members$"),
    ):
        case.edit(manager)


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_relationship_manager_peers_can_be_replaced_and_appended(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    manager = tags_of(make_node(client_type, clients, location_schema, location_payload()))
    unknown_manager = tags_of(make_node(client_type, clients, location_schema, location_payload(omit={"tags"})))

    with no_field_warning():
        existing = manager.peers
        manager.peers = []
        assert manager.peer_ids == []

        manager.peers.append(existing[0])
        assert manager.peer_ids == [TAG_ID]
        assert manager.peers == existing

        unknown_manager.peers = existing
        assert unknown_manager.initialized is False


# SDK-internal reads


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_storing_partial_node_is_silent(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    client = client_for(client_type, clients)
    node = make_node(client_type, clients, location_schema, location_payload(omit={"description", "tags"}))

    with no_field_warning():
        store_node(clients, node)
        assert client.store.get(key=LOCATION_ID) is node


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_hfid_through_unknown_relationship_is_none_and_node_is_stored_by_id(
    clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI], client_type: str
) -> None:
    client = client_for(client_type, clients)
    rack_payload = {
        "node": {
            "__typename": "BuiltinRack",
            "id": RACK_ID,
            "hfid": None,
            "display_label": "RACK1",
            "facility_id": {"value": "RACK1"},
            "description": {"value": None},
            "tags": {"count": 0, "edges": []},
            "member_of_groups": {"count": 0, "edges": []},
        }
    }
    rack = make_node(client_type, clients, schema_with_hfid["rack"], rack_payload)

    with no_field_warning():
        assert rack.location.is_loaded is False
        assert rack.hfid is None
        assert rack.hfid_str is None

        store_node(clients, rack)
        assert client.store.get(key=RACK_ID) is rack

    with pytest.raises(NodeNotFoundError, match=re.escape("Unable to find the node 'BuiltinRack__RACK1__DFW'")):
        client.store.get(key="BuiltinRack__RACK1__DFW")


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_update_of_partial_node_sends_only_id_and_modified_attribute(
    httpx_mock: HTTPXMock, clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinLocationUpdate": {"ok": True, "object": {"id": LOCATION_ID}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-builtinlocation-update"},
    )
    node = make_node(client_type, clients, location_schema, location_payload(omit={"description", "tags"}))

    with no_field_warning():
        attribute_of(node, "name").value = "DFW2"
        await save_node(node)

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert mutation_input(requests[0]) == {"name": {"value": "DFW2"}, "id": LOCATION_ID}


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_upsert_of_new_node_is_silent(
    httpx_mock: HTTPXMock, clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI], client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinRackUpsert": {"ok": True, "object": {"id": RACK_ID}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-builtinrack-upsert"},
    )
    client = client_for(client_type, clients)
    rack = make_node(client_type, clients, schema_with_hfid["rack"], {"facility_id": {"value": "RACK1"}})

    # Once saved, the rack has an id, so its never-set location becomes unknown while the
    # save stores it and computes its HFID through that location.
    with no_field_warning():
        await save_node(rack, allow_upsert=True)

        assert rack.id == RACK_ID
        assert rack.location.is_loaded is False
        assert rack.hfid is None
        assert client.store.get(key=RACK_ID) is rack


@pytest.mark.usefixtures("strict_switch")
@pytest.mark.parametrize("client_type", client_types)
async def test_path_value_through_unknown_fields_is_silent(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    node = make_node(client_type, clients, location_schema, location_payload(omit={"description", "primary_tag"}))

    with no_field_warning():
        assert node.get_path_value("primary_tag__name__value") is None
        assert node.get_path_value("description__value") is None


# Strictness


SELECTION_ADVICE = "Add it to the selection before reading it."
SELECTION_OR_FETCH_ADVICE = "Add it to the selection, or call fetch() on it, before reading it."


@dataclass
class StrictReadCase:
    name: str
    field: str
    read: Callable[[Any], Any]
    advice: str


STRICT_READ_CASES = [
    StrictReadCase(
        name="attribute", field="description", read=attrgetter("description.value"), advice=SELECTION_ADVICE
    ),
    StrictReadCase(
        name="cardinality-one", field="primary_tag", read=attrgetter("primary_tag.id"), advice=SELECTION_ADVICE
    ),
    StrictReadCase(
        name="cardinality-many", field="tags", read=attrgetter("tags.peers"), advice=SELECTION_OR_FETCH_ADVICE
    ),
]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in STRICT_READ_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_unknown_read_raises_on_node_with_strict_selection(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, case: StrictReadCase
) -> None:
    node = make_node(client_type, clients, location_schema, location_payload(omit={case.field}))
    node._selection = Selection.from_args(only=["name"])

    message = f"BuiltinLocation.{case.field} was not fetched (selection: only=['name']). {case.advice}"
    with pytest.raises(FieldNotLoadedError, match=exactly(message)) as exc_info:
        case.read(node)

    assert (exc_info.value.kind, exc_info.value.field, exc_info.value.selection) == (
        "BuiltinLocation",
        case.field,
        "only=['name']",
    )


@pytest.mark.parametrize("client_type", client_types)
async def test_unknown_read_warning_names_non_strict_selection(
    clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    node = make_node(client_type, clients, location_schema, location_payload(omit={"description"}))
    node._selection = Selection.from_args(exclude=["description"])

    message = (
        "BuiltinLocation.description was not fetched (selection: exclude=['description']). "
        "Add it to the selection before reading it." + WARNING_SUFFIX
    )
    with pytest.warns(FieldNotLoadedWarning, match=exactly(message)):
        assert node.description.value is None


@pytest.mark.parametrize("client_type", client_types)
async def test_strict_switch_alone_turns_the_warning_of_a_fetched_node_into_the_error(
    request: pytest.FixtureRequest,
    httpx_mock: HTTPXMock,
    clients: BothClients,
    location_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    client_for(client_type, clients).schema.set_cache({"version": "1.0", "nodes": [location_schema.model_dump()]})
    httpx_mock.add_response(
        method="POST",
        json={"data": {"BuiltinLocation": {"count": 1, "edges": [location_payload(omit={"description"})]}}},
        match_headers={"X-Infrahub-Tracker": "query-builtinlocation-page1"},
    )
    nodes: list[InfrahubNode] | list[InfrahubNodeSync]
    if client_type == "standard":
        nodes = await clients.standard.filters(kind="BuiltinLocation", exclude=["description"])
    else:
        nodes = clients.sync.filters(kind="BuiltinLocation", exclude=["description"])
    node = nodes[0]
    message = (
        "BuiltinLocation.description was not fetched (selection: exclude=['description']). "
        "Add it to the selection before reading it."
    )

    with pytest.warns(FieldNotLoadedWarning, match=exactly(message + WARNING_SUFFIX)) as record:
        assert node.description.value is None

    request.getfixturevalue("strict_access")
    with pytest.raises(FieldNotLoadedError, match=exactly(message)) as exc_info:
        _ = node.description.value

    assert [str(item.message) for item in record] == [str(exc_info.value) + WARNING_SUFFIX]
    assert (exc_info.value.kind, exc_info.value.field, exc_info.value.selection) == (
        "BuiltinLocation",
        "description",
        "exclude=['description']",
    )
