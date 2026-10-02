"""Tests for hydrating relationship peers with a chosen set of fields."""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest
from graphql import FieldNode, OperationDefinitionNode, parse

from infrahub_sdk.exceptions import (
    FieldNotLoadedError,
    FieldNotLoadedWarning,
    SelectionConflictError,
    SelectionFieldNotFoundError,
)
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.schema import (
    GenericSchemaAPI,
    NodeSchemaAPI,
    RelationshipCardinality,
    RelationshipKind,
    RelationshipSchemaAPI,
)

if TYPE_CHECKING:
    import httpx
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.node import RelatedNode, RelatedNodeSync, RelationshipManager, RelationshipManagerSync
    from infrahub_sdk.schema import MainSchemaTypesAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]


@pytest.fixture
async def core_node_schema() -> GenericSchemaAPI:
    return GenericSchemaAPI(namespace="Core", name="Node", used_by=["TestDevice", "TestCable"])


@pytest.fixture
async def group_with_members_schema(std_group_schema: NodeSchemaAPI) -> NodeSchemaAPI:
    members = RelationshipSchemaAPI(
        name="members",
        peer="CoreNode",
        kind=RelationshipKind.GENERIC,
        cardinality=RelationshipCardinality.MANY,
        optional=True,
        identifier="group_member",
    )
    return std_group_schema.model_copy(update={"relationships": [*std_group_schema.relationships, members]})


@pytest.fixture
async def named_member_schema() -> NodeSchemaAPI:
    return NodeSchemaAPI(
        namespace="Test",
        name="Device",
        default_filter="name__value",
        inherit_from=["CoreNode"],
        attributes=[
            {"name": "name", "kind": "Text", "unique": True},
            {"name": "description", "kind": "Text", "optional": True},
        ],
    )


@pytest.fixture
async def nameless_member_schema() -> NodeSchemaAPI:
    return NodeSchemaAPI(
        namespace="Test",
        name="Cable",
        default_filter="serial__value",
        inherit_from=["CoreNode"],
        attributes=[{"name": "serial", "kind": "Text", "unique": True}],
    )


@pytest.fixture
async def hydration_clients(
    clients: BothClients,
    core_node_schema: GenericSchemaAPI,
    group_with_members_schema: NodeSchemaAPI,
    named_member_schema: NodeSchemaAPI,
    nameless_member_schema: NodeSchemaAPI,
) -> BothClients:
    cache_data = {
        "version": "1.0",
        "generics": [core_node_schema.model_dump()],
        "nodes": [
            group_with_members_schema.model_dump(),
            named_member_schema.model_dump(),
            nameless_member_schema.model_dump(),
        ],
    }
    clients.standard.schema.set_cache(cache_data)
    clients.sync.schema.set_cache(cache_data)
    return clients


@pytest.mark.parametrize("client_type", client_types)
async def test_group_members_resolve_from_schema_cache(hydration_clients: BothClients, client_type: str) -> None:
    kinds = ["CoreStandardGroup", "CoreNode", "TestDevice", "TestCable"]
    schemas: dict[str, MainSchemaTypesAPI]
    if client_type == "standard":
        schemas = {kind: await hydration_clients.standard.schema.get(kind=kind) for kind in kinds}
    else:
        schemas = {kind: hydration_clients.sync.schema.get(kind=kind) for kind in kinds}

    group = schemas["CoreStandardGroup"]
    assert isinstance(group, NodeSchemaAPI)
    assert group.attribute_names == ["name", "description"]
    members = group.get_relationship(name="members")
    assert (members.peer, members.kind, members.cardinality) == ("CoreNode", "Generic", "many")

    core_node = schemas["CoreNode"]
    assert isinstance(core_node, GenericSchemaAPI)
    assert core_node.used_by == ["TestDevice", "TestCable"]

    for kind, attribute_names in (("TestDevice", ["name", "description"]), ("TestCable", ["serial"])):
        member = schemas[kind]
        assert isinstance(member, NodeSchemaAPI)
        assert member.inherit_from == ["CoreNode"]
        assert member.attribute_names == attribute_names


GRAPHQL_URL = "http://mock/graphql/main"
GROUP_ID = "1d8e4c2a-6f3b-4a5e-9c7d-2b1a0f9e8d71"
DEVICE_ID = "2e9f5d3b-7a4c-4b6f-8d8e-3c2b1a0f9e82"
CABLE_ID = "3fa06e4c-8b5d-4c7a-9e9f-4d3c2b1a0f93"

ONLY_FLOOR_FIELDS = ["id", "display_label", "__typename"]
DEFAULT_FLOOR_FIELDS = ["id", "hfid", "display_label", "__typename"]

GROUP_DATA: dict[str, Any] = {
    "id": GROUP_ID,
    "display_label": "lab",
    "__typename": "CoreStandardGroup",
    "name": {"value": "lab"},
    "description": {"value": None},
}
DEVICE_FLOOR: dict[str, Any] = {"id": DEVICE_ID, "display_label": "edge01", "__typename": "TestDevice"}
CABLE_FLOOR: dict[str, Any] = {"id": CABLE_ID, "display_label": "cable-1", "__typename": "TestCable"}
MEMBERS_DATA: dict[str, Any] = {
    "count": 2,
    "edges": [{"node": {**DEVICE_FLOOR, "hfid": None}}, {"node": {**CABLE_FLOOR, "hfid": None}}],
}
GROUP_WITH_MEMBERS_DATA: dict[str, Any] = {**GROUP_DATA, "members": MEMBERS_DATA}
# Both peer batches count their kind before querying it; the count queries carry no tracker.
PEER_COUNTS: dict[str, Any] = {"data": {"TestDevice": {"count": 1}, "TestCable": {"count": 1}}}


def _response(kind: str, node: dict[str, Any]) -> dict[str, Any]:
    return {"data": {kind: {"count": 1, "edges": [{"node": node}]}}}


def _add_data_response(httpx_mock: HTTPXMock, kind: str, node: dict[str, Any]) -> None:
    httpx_mock.add_response(
        method="POST",
        url=GRAPHQL_URL,
        json=_response(kind, node),
        match_headers={"X-Infrahub-Tracker": f"query-{kind.lower()}-page1"},
    )


def _add_peer_count_response(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=GRAPHQL_URL, json=PEER_COUNTS, is_reusable=True)


def _child(parent: FieldNode, name: str) -> FieldNode:
    assert parent.selection_set is not None
    return next(
        child for child in parent.selection_set.selections if isinstance(child, FieldNode) and child.name.value == name
    )


def _selected_fields(request: httpx.Request) -> tuple[str, list[str]]:
    """Return the kind a node query asks for and the names it selects on each returned node."""
    operation = parse(json.loads(request.content)["query"]).definitions[0]
    assert isinstance(operation, OperationDefinitionNode)
    kind_field = operation.selection_set.selections[0]
    assert isinstance(kind_field, FieldNode)
    node = _child(_child(kind_field, "edges"), "node")
    assert node.selection_set is not None
    return kind_field.name.value, [
        child.name.value for child in node.selection_set.selections if isinstance(child, FieldNode)
    ]


def _data_queries(httpx_mock: HTTPXMock) -> list[tuple[str, list[str]]]:
    """Return the kind and node fields of every data query sent, sorted by kind; count queries are skipped."""
    return sorted(
        _selected_fields(request) for request in httpx_mock.get_requests() if "x-infrahub-tracker" in request.headers
    )


def _group(
    clients: BothClients, client_type: str, schema: NodeSchemaAPI, data: dict[str, Any]
) -> InfrahubNode | InfrahubNodeSync:
    if client_type == "standard":
        return InfrahubNode(client=clients.standard, schema=schema, data=data)
    return InfrahubNodeSync(client=clients.sync, schema=schema, data=data)


async def _fetch(
    target: RelatedNode | RelatedNodeSync | RelationshipManager | RelationshipManagerSync,
    only: list[str] | None = None,
    exclude: list[str] | None = None,
) -> None:
    result = target.fetch(only=only, exclude=exclude)
    if inspect.isawaitable(result):
        await result


def _store_node(clients: BothClients, client_type: str, schema: NodeSchemaAPI, data: dict[str, Any]) -> None:
    if client_type == "standard":
        clients.standard.store.set(node=InfrahubNode(client=clients.standard, schema=schema, data=data))
    else:
        clients.sync.store.set(node=InfrahubNodeSync(client=clients.sync, schema=schema, data=data))


@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_fetch_with_only_queries_the_named_fields_of_the_peer_kind(
    httpx_mock: HTTPXMock, hydration_clients: BothClients, group_with_members_schema: NodeSchemaAPI, client_type: str
) -> None:
    _add_data_response(httpx_mock, "TestDevice", {**DEVICE_FLOOR, "name": {"value": "edge01"}})
    client = hydration_clients.standard if client_type == "standard" else hydration_clients.sync
    group = _group(hydration_clients, client_type, group_with_members_schema, GROUP_WITH_MEMBERS_DATA)
    related = group._get_relationship_many(name="members")[0]

    await _fetch(related, only=["name"])

    assert len(httpx_mock.get_requests()) == 1
    assert _data_queries(httpx_mock) == [("TestDevice", [*ONLY_FLOOR_FIELDS, "name"])]
    peer = related.peer
    assert client.store.get(key=DEVICE_ID) is peer
    assert (peer.id, peer.display_label, peer.name.value) == (DEVICE_ID, "edge01", "edge01")
    message = (
        "TestDevice.description was not fetched (selection: only=['name']). Add it to the selection before reading it."
    )
    with pytest.raises(FieldNotLoadedError, match=f"^{re.escape(message)}$") as exc:
        _ = peer.description.value
    assert (exc.value.kind, exc.value.field, exc.value.selection) == ("TestDevice", "description", "only=['name']")


@pytest.mark.parametrize("only", [pytest.param(["name"], id="name"), pytest.param(["name", "id", "hfid"], id="floor")])
@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_fetch_with_only_leaves_a_peer_of_a_kind_lacking_the_names_as_a_reference(
    httpx_mock: HTTPXMock,
    hydration_clients: BothClients,
    group_with_members_schema: NodeSchemaAPI,
    nameless_member_schema: NodeSchemaAPI,
    client_type: str,
    only: list[str],
) -> None:
    client = hydration_clients.standard if client_type == "standard" else hydration_clients.sync
    _store_node(hydration_clients, client_type, nameless_member_schema, {**CABLE_FLOOR, "serial": {"value": "SN-1"}})
    stored_cable = client.store.get(key=CABLE_ID)
    group = _group(hydration_clients, client_type, group_with_members_schema, GROUP_WITH_MEMBERS_DATA)
    related = group._get_relationship_many(name="members")[1]

    await _fetch(related, only=only)

    assert httpx_mock.get_requests() == []
    assert client.store.get(key=CABLE_ID) is stored_cable
    assert related.peer is stored_cable
    assert stored_cable.serial.value == "SN-1"


@pytest.mark.parametrize("client_type", client_types)
async def test_manager_fetch_with_only_sends_one_query_per_peer_kind(
    httpx_mock: HTTPXMock,
    hydration_clients: BothClients,
    group_with_members_schema: NodeSchemaAPI,
    nameless_member_schema: NodeSchemaAPI,
    client_type: str,
) -> None:
    _add_data_response(httpx_mock, "TestDevice", {**DEVICE_FLOOR, "name": {"value": "edge01"}})
    _add_peer_count_response(httpx_mock)
    client = hydration_clients.standard if client_type == "standard" else hydration_clients.sync
    _store_node(hydration_clients, client_type, nameless_member_schema, {**CABLE_FLOOR, "serial": {"value": "SN-1"}})
    stored_cable = client.store.get(key=CABLE_ID)
    group = _group(hydration_clients, client_type, group_with_members_schema, GROUP_WITH_MEMBERS_DATA)
    members = group._get_relationship_many(name="members")

    await _fetch(members, only=["name"])

    # TestCable defines none of the names, so its peers stay references and its stored node is left alone.
    assert _data_queries(httpx_mock) == [("TestDevice", [*ONLY_FLOOR_FIELDS, "name"])]
    device = client.store.get(key=DEVICE_ID)
    assert client.store.get(key=CABLE_ID) is stored_cable
    assert [members[0].peer, members[1].peer] == [device, stored_cable]
    assert (device.name.value, stored_cable.serial.value) == ("edge01", "SN-1")
    with pytest.raises(
        FieldNotLoadedError, match=re.escape("TestDevice.description was not fetched (selection: only=['name'])")
    ):
        _ = device.description.value


@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_fetch_with_exclude_queries_the_default_fields_minus_the_excluded_ones(
    httpx_mock: HTTPXMock, hydration_clients: BothClients, group_with_members_schema: NodeSchemaAPI, client_type: str
) -> None:
    _add_data_response(httpx_mock, "TestDevice", {**DEVICE_FLOOR, "hfid": None, "name": {"value": "edge01"}})
    client = hydration_clients.standard if client_type == "standard" else hydration_clients.sync
    group = _group(hydration_clients, client_type, group_with_members_schema, GROUP_WITH_MEMBERS_DATA)
    related = group._get_relationship_many(name="members")[0]

    await _fetch(related, exclude=["description"])

    assert _data_queries(httpx_mock) == [("TestDevice", [*DEFAULT_FLOOR_FIELDS, "name"])]
    peer = related.peer
    assert client.store.get(key=DEVICE_ID) is peer
    assert peer.name.value == "edge01"
    # A peer hydrated without only keeps the 1.x behaviour: an unknown read warns.
    message = (
        "TestDevice.description was not fetched (selection: exclude=['description']). "
        "Add it to the selection before reading it. This will raise FieldNotLoadedError in infrahub-sdk 2.0."
    )
    with pytest.warns(FieldNotLoadedWarning, match=f"^{re.escape(message)}$") as record:
        assert peer.description.value is None
    assert [str(item.message) for item in record] == [message]


@dataclass
class FetchTargetCase:
    name: str
    group_data: dict[str, Any]
    member_index: int | None = None


# The uninitialized manager would re-query its group first, so it shows that validation precedes that request.
FETCH_TARGET_CASES = [
    FetchTargetCase(name="related-node", group_data=GROUP_WITH_MEMBERS_DATA, member_index=0),
    FetchTargetCase(name="uninitialized-manager", group_data=GROUP_DATA),
]


def _fetch_target(
    clients: BothClients, client_type: str, schema: NodeSchemaAPI, case: FetchTargetCase
) -> RelatedNode | RelatedNodeSync | RelationshipManager | RelationshipManagerSync:
    members = _group(clients, client_type, schema, case.group_data)._get_relationship_many(name="members")
    if case.member_index is None:
        return members
    return members[case.member_index]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in FETCH_TARGET_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_fetch_with_unknown_name_is_rejected_before_any_request(
    httpx_mock: HTTPXMock,
    hydration_clients: BothClients,
    group_with_members_schema: NodeSchemaAPI,
    client_type: str,
    case: FetchTargetCase,
) -> None:
    target = _fetch_target(hydration_clients, client_type, group_with_members_schema, case)

    with pytest.raises(
        SelectionFieldNotFoundError, match=re.escape("'model' is not an attribute or relationship of CoreNode.")
    ) as exc:
        await _fetch(target, only=["name", "model"])

    assert (exc.value.kind, exc.value.field, exc.value.implementing_kinds) == ("CoreNode", "model", [])
    assert httpx_mock.get_requests() == []


@dataclass
class FetchConflictCase:
    name: str
    target: FetchTargetCase
    exclude: list[str] = field(default_factory=list)


FETCH_CONFLICT_CASES = [
    FetchConflictCase(name=f"{target.name}-{label}", target=target, exclude=exclude)
    for target in FETCH_TARGET_CASES
    for label, exclude in (("exclude", ["description"]), ("empty-exclude", []))
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in FETCH_CONFLICT_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_fetch_with_only_and_exclude_is_rejected_before_any_request(
    httpx_mock: HTTPXMock,
    clients: BothClients,
    group_with_members_schema: NodeSchemaAPI,
    client_type: str,
    case: FetchConflictCase,
) -> None:
    # No schema is cached, so even resolving the peer kind would send a request.
    target = _fetch_target(clients, client_type, group_with_members_schema, case.target)

    with pytest.raises(
        SelectionConflictError, match=re.escape("'only' cannot be combined with 'exclude'; pass 'only' on its own.")
    ) as exc:
        await _fetch(target, only=["name"], exclude=case.exclude)

    assert exc.value.parameters == ["only", "exclude"]
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("client_type", client_types)
async def test_uninitialized_manager_fetch_requeries_only_the_relationship(
    httpx_mock: HTTPXMock, hydration_clients: BothClients, group_with_members_schema: NodeSchemaAPI, client_type: str
) -> None:
    group_floor = {name: GROUP_DATA[name] for name in ONLY_FLOOR_FIELDS}
    _add_data_response(httpx_mock, "CoreStandardGroup", {**group_floor, "members": MEMBERS_DATA})
    _add_data_response(httpx_mock, "TestDevice", {**DEVICE_FLOOR, "name": {"value": "edge01"}})
    _add_peer_count_response(httpx_mock)
    client = hydration_clients.standard if client_type == "standard" else hydration_clients.sync
    group = _group(hydration_clients, client_type, group_with_members_schema, GROUP_DATA)
    if isinstance(group, InfrahubNode):
        hydration_clients.standard.store.set(node=group)
    else:
        hydration_clients.sync.store.set(node=group)
    members = group._get_relationship_many(name="members")

    await _fetch(members, only=["name"])

    assert _selected_fields(httpx_mock.get_requests()[0]) == ("CoreStandardGroup", [*ONLY_FLOOR_FIELDS, "members"])
    assert _data_queries(httpx_mock) == [
        ("CoreStandardGroup", [*ONLY_FLOOR_FIELDS, "members"]),
        ("TestDevice", [*ONLY_FLOOR_FIELDS, "name"]),
    ]
    assert members.peer_ids == [DEVICE_ID, CABLE_ID]
    assert client.store.get(key=GROUP_ID) is group


@dataclass
class DefaultFetchCase:
    name: str
    exclude: list[str] | None
    device_node: dict[str, Any]
    expected_queries: list[tuple[str, list[str]]]
    description_loaded: bool


DEFAULT_FETCH_CASES = [
    DefaultFetchCase(
        name="no-arguments",
        exclude=None,
        device_node={**DEVICE_FLOOR, "hfid": None, "name": {"value": "edge01"}, "description": {"value": "Edge"}},
        expected_queries=[
            ("TestCable", [*DEFAULT_FLOOR_FIELDS, "serial"]),
            ("TestDevice", [*DEFAULT_FLOOR_FIELDS, "name", "description"]),
        ],
        description_loaded=True,
    ),
    DefaultFetchCase(
        name="exclude",
        exclude=["description"],
        device_node={**DEVICE_FLOOR, "hfid": None, "name": {"value": "edge01"}},
        expected_queries=[
            ("TestCable", [*DEFAULT_FLOOR_FIELDS, "serial"]),
            ("TestDevice", [*DEFAULT_FLOOR_FIELDS, "name"]),
        ],
        description_loaded=False,
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in DEFAULT_FETCH_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_manager_fetch_without_only_keeps_the_default_selection(
    httpx_mock: HTTPXMock,
    hydration_clients: BothClients,
    group_with_members_schema: NodeSchemaAPI,
    client_type: str,
    case: DefaultFetchCase,
) -> None:
    _add_data_response(httpx_mock, "TestDevice", case.device_node)
    _add_data_response(httpx_mock, "TestCable", {**CABLE_FLOOR, "hfid": None, "serial": {"value": "SN-1"}})
    _add_peer_count_response(httpx_mock)
    client = hydration_clients.standard if client_type == "standard" else hydration_clients.sync
    group = _group(hydration_clients, client_type, group_with_members_schema, GROUP_WITH_MEMBERS_DATA)
    members = group._get_relationship_many(name="members")

    await _fetch(members, exclude=case.exclude)

    assert _data_queries(httpx_mock) == case.expected_queries
    device = client.store.get(key=DEVICE_ID)
    cable = client.store.get(key=CABLE_ID)
    assert [members[0].peer, members[1].peer] == [device, cable]
    assert (device.name.value, cable.serial.value) == ("edge01", "SN-1")
    assert device.description.is_loaded is case.description_loaded
