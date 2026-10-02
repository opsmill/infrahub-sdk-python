"""Tests for the fields a node query selects, including exclusive selection with ``only``."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import (
    FieldNotLoadedError,
    FieldNotLoadedWarning,
    NodeInvalidError,
    NodeNotFoundError,
    SelectionConflictError,
    SelectionFieldNotFoundError,
)
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.schema import GenericSchemaAPI, NodeSchema, NodeSchemaAPI
from tests.unit.sdk.test_node_field_access import attribute_of, mutation_input, no_field_warning

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import MainSchemaTypesAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

GENERIC_DEVICE_ATTRIBUTES: list[dict[str, Any]] = [
    {"name": "name", "kind": "Text", "unique": True},
    {"name": "description", "kind": "Text", "optional": True},
]
GENERIC_DEVICE_RELATIONSHIPS: list[dict[str, Any]] = [
    {"name": "tags", "peer": "BuiltinTag", "kind": "Generic", "cardinality": "many", "optional": True},
]


def _implementing_device_schema(name: str, extra_attribute: dict[str, Any]) -> NodeSchemaAPI:
    # The server repeats inherited fields on each implementing kind, flagged with ``inherited``.
    return NodeSchemaAPI(
        namespace="Test",
        name=name,
        default_filter="name__value",
        inherit_from=["TestGenericDevice"],
        attributes=[{**attr, "inherited": True} for attr in GENERIC_DEVICE_ATTRIBUTES] + [extra_attribute],
        relationships=[{**rel, "inherited": True} for rel in GENERIC_DEVICE_RELATIONSHIPS],
    )


@pytest.fixture
async def generic_device_schema() -> GenericSchemaAPI:
    return GenericSchemaAPI(
        namespace="Test",
        name="GenericDevice",
        default_filter="name__value",
        attributes=GENERIC_DEVICE_ATTRIBUTES,
        relationships=GENERIC_DEVICE_RELATIONSHIPS,
        used_by=["TestRouter", "TestSwitch"],
    )


@pytest.fixture
async def router_schema() -> NodeSchemaAPI:
    return _implementing_device_schema("Router", {"name": "role", "kind": "Text", "optional": True})


@pytest.fixture
async def switch_schema() -> NodeSchemaAPI:
    return _implementing_device_schema("Switch", {"name": "ports", "kind": "Number", "optional": True})


@pytest.fixture
async def generic_family_clients(
    clients: BothClients,
    generic_device_schema: GenericSchemaAPI,
    router_schema: NodeSchemaAPI,
    switch_schema: NodeSchemaAPI,
    tag_schema: NodeSchemaAPI,
    location_schema: NodeSchemaAPI,
) -> BothClients:
    cache_data = {
        "version": "1.0",
        "generics": [generic_device_schema.model_dump()],
        "nodes": [
            router_schema.model_dump(),
            switch_schema.model_dump(),
            tag_schema.model_dump(),
            location_schema.model_dump(),
        ],
    }
    clients.standard.schema.set_cache(cache_data)
    clients.sync.schema.set_cache(cache_data)
    return clients


@pytest.mark.parametrize("client_type", client_types)
async def test_generic_family_resolves_from_schema_cache(generic_family_clients: BothClients, client_type: str) -> None:
    kinds = ["TestGenericDevice", "TestRouter", "TestSwitch", "BuiltinTag", "BuiltinLocation"]
    schemas: dict[str, MainSchemaTypesAPI]
    if client_type == "standard":
        schemas = {kind: await generic_family_clients.standard.schema.get(kind=kind) for kind in kinds}
    else:
        schemas = {kind: generic_family_clients.sync.schema.get(kind=kind) for kind in kinds}

    generic = schemas["TestGenericDevice"]
    assert isinstance(generic, GenericSchemaAPI)
    assert generic.used_by == ["TestRouter", "TestSwitch"]
    assert generic.attribute_names == ["name", "description"]
    assert generic.relationship_names == ["tags"]
    assert generic.get_relationship(name="tags").kind == "Generic"

    for kind, own_attribute in (("TestRouter", "role"), ("TestSwitch", "ports")):
        implementing = schemas[kind]
        assert isinstance(implementing, NodeSchemaAPI)
        assert implementing.inherit_from == ["TestGenericDevice"]
        assert implementing.attribute_names == ["name", "description", own_attribute]
        assert [attr.name for attr in implementing.attributes if not attr.inherited] == [own_attribute]
        assert implementing.relationship_names == ["tags"]

    assert isinstance(schemas["BuiltinTag"], NodeSchemaAPI)
    assert isinstance(schemas["BuiltinLocation"], NodeSchemaAPI)
    assert schemas["BuiltinLocation"].relationship_names == ["tags", "primary_tag", "member_of_groups"]


FLOOR: dict[str, Any] = {"id": None, "display_label": None, "__typename": None}
PEER_FLOOR: dict[str, Any] = {"id": None, "hfid": None, "display_label": None, "__typename": None}
VALUE: dict[str, Any] = {"value": None}
TAG_DEFAULT_PEER: dict[str, Any] = {**PEER_FLOOR, "name": VALUE, "description": VALUE}
HIERARCHY_DEFAULT_PEER: dict[str, Any] = {**PEER_FLOOR, "name": VALUE, "description": VALUE}


def _query(kind: str, node: dict[str, Any]) -> dict[str, Any]:
    return {kind: {"count": None, "edges": {"node": node}, "@filters": {}}}


async def _generate_query(
    clients: BothClients, client_type: str, schema: MainSchemaTypesAPI, kwargs: dict[str, Any] | None = None
) -> dict[str, Any]:
    kwargs = kwargs or {}
    if client_type == "standard":
        return await InfrahubNode(client=clients.standard, schema=schema).generate_query_data(**kwargs)
    return InfrahubNodeSync(client=clients.sync, schema=schema).generate_query_data(**kwargs)


@pytest.fixture
async def rack_schema() -> NodeSchemaAPI:
    return NodeSchema(
        name="Rack",
        namespace="Test",
        default_filter="name__value",
        attributes=[{"name": "name", "kind": "Text", "unique": True}],
        relationships=[
            {"name": "tags", "peer": "BuiltinTag", "optional": True, "cardinality": "many", "kind": "Attribute"},
        ],
    ).convert_api()


@pytest.fixture
async def hierarchical_schema() -> NodeSchemaAPI:
    schema = NodeSchema(
        name="Location",
        namespace="Infra",
        default_filter="name__value",
        attributes=[
            {"name": "name", "kind": "Text", "unique": True},
            {"name": "description", "kind": "Text", "optional": True},
        ],
        relationships=[
            {"name": "parent", "peer": "InfraLocation", "optional": True, "cardinality": "one", "kind": "Hierarchy"},
            {"name": "children", "peer": "InfraLocation", "optional": True, "cardinality": "many", "kind": "Hierarchy"},
        ],
    ).convert_api()
    # The server sets ``hierarchy``; it is not part of the user-facing ``NodeSchema``.
    schema.hierarchy = "InfraLocation"
    return schema


@pytest.fixture
async def hierarchical_clients(clients: BothClients, hierarchical_schema: NodeSchemaAPI) -> BothClients:
    cache_data = {"version": "1.0", "nodes": [hierarchical_schema.model_dump()]}
    clients.standard.schema.set_cache(cache_data)
    clients.sync.schema.set_cache(cache_data)
    return clients


@dataclass
class QueryShapeCase:
    name: str
    kwargs: dict[str, Any]
    expected_node: dict[str, Any]


TAG_ONLY_CASES = [
    QueryShapeCase(name="attribute", kwargs={"only": ["name"]}, expected_node={**FLOOR, "name": VALUE}),
    QueryShapeCase(name="empty", kwargs={"only": []}, expected_node=FLOOR),
    QueryShapeCase(
        name="hfid", kwargs={"only": ["name", "hfid"]}, expected_node={**FLOOR, "hfid": None, "name": VALUE}
    ),
    QueryShapeCase(name="floor-names", kwargs={"only": ["id", "display_label"]}, expected_node=FLOOR),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in TAG_ONLY_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_shape_on_tag(
    generic_family_clients: BothClients, tag_schema: NodeSchemaAPI, client_type: str, case: QueryShapeCase
) -> None:
    query = await _generate_query(generic_family_clients, client_type, tag_schema, case.kwargs)

    assert query == _query("BuiltinTag", case.expected_node)


LOCATION_ONLY_CASES = [
    QueryShapeCase(
        name="cardinality-one-floor",
        kwargs={"only": ["primary_tag"]},
        expected_node={**FLOOR, "primary_tag": {"node": PEER_FLOOR}},
    ),
    QueryShapeCase(
        name="cardinality-many-floor",
        kwargs={"only": ["tags"]},
        expected_node={**FLOOR, "tags": {"edges": {"node": PEER_FLOOR}}},
    ),
    QueryShapeCase(
        name="prefetch-cardinality-many",
        kwargs={"only": ["name", "tags"], "prefetch_relationships": True},
        expected_node={**FLOOR, "name": VALUE, "tags": {"edges": {"node": TAG_DEFAULT_PEER}}},
    ),
    QueryShapeCase(
        name="prefetch-cardinality-one",
        kwargs={"only": ["primary_tag"], "prefetch_relationships": True},
        expected_node={**FLOOR, "primary_tag": {"node": TAG_DEFAULT_PEER}},
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in LOCATION_ONLY_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_shape_on_location(
    generic_family_clients: BothClients, location_schema: NodeSchemaAPI, client_type: str, case: QueryShapeCase
) -> None:
    query = await _generate_query(generic_family_clients, client_type, location_schema, case.kwargs)

    assert query == _query("BuiltinLocation", case.expected_node)


@pytest.mark.parametrize("client_type", client_types)
async def test_only_omits_unnamed_attribute_kind_many_relationship(
    clients: BothClients, rack_schema: NodeSchemaAPI, client_type: str
) -> None:
    default_query = await _generate_query(clients, client_type, rack_schema)
    only_query = await _generate_query(clients, client_type, rack_schema, {"only": ["name"]})

    assert default_query == _query("TestRack", {**PEER_FLOOR, "name": VALUE, "tags": {"edges": {"node": PEER_FLOOR}}})
    assert only_query == _query("TestRack", {**FLOOR, "name": VALUE})


HIERARCHICAL_ONLY_CASES = [
    QueryShapeCase(name="not-named", kwargs={"only": ["name"]}, expected_node={**FLOOR, "name": VALUE}),
    QueryShapeCase(
        name="not-named-with-prefetch",
        kwargs={"only": ["name"], "prefetch_relationships": True},
        expected_node={**FLOOR, "name": VALUE},
    ),
    QueryShapeCase(
        name="named-floor",
        kwargs={"only": ["parent", "children", "ancestors", "descendants"]},
        expected_node={
            **FLOOR,
            "parent": {"node": {"...on InfraLocation": PEER_FLOOR}},
            "children": {"edges": {"node": {"...on InfraLocation": PEER_FLOOR}}},
            "ancestors": {"edges": {"node": {"...on InfraLocation": PEER_FLOOR}}},
            "descendants": {"edges": {"node": {"...on InfraLocation": PEER_FLOOR}}},
        },
    ),
    QueryShapeCase(
        name="named-with-prefetch",
        kwargs={"only": ["parent", "descendants"], "prefetch_relationships": True},
        expected_node={
            **FLOOR,
            "parent": {"node": {"...on InfraLocation": HIERARCHY_DEFAULT_PEER}},
            "descendants": {"edges": {"node": {"...on InfraLocation": HIERARCHY_DEFAULT_PEER}}},
        },
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in HIERARCHICAL_ONLY_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_shape_on_hierarchical_kind(
    hierarchical_clients: BothClients, hierarchical_schema: NodeSchemaAPI, client_type: str, case: QueryShapeCase
) -> None:
    query = await _generate_query(hierarchical_clients, client_type, hierarchical_schema, case.kwargs)

    assert query == _query("InfraLocation", case.expected_node)


GENERIC_ONLY_CASES = [
    QueryShapeCase(
        name="generic-and-router-names",
        kwargs={"only": ["name", "role"], "fragment": True},
        expected_node={
            **FLOOR,
            "name": VALUE,
            "...on TestRouter": {"role": {"value": None, "@alias": "__alias__TestRouter__role"}},
        },
    ),
    QueryShapeCase(
        name="generic-relationship-and-switch-name",
        kwargs={"only": ["tags", "ports"], "fragment": True},
        expected_node={
            **FLOOR,
            "tags": {"edges": {"node": PEER_FLOOR}},
            "...on TestSwitch": {"ports": {"value": None, "@alias": "__alias__TestSwitch__ports"}},
        },
    ),
    QueryShapeCase(
        name="generic-names-only",
        kwargs={"only": ["name"], "fragment": True},
        expected_node={**FLOOR, "name": VALUE},
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in GENERIC_ONLY_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_shape_on_generic_with_fragments(
    generic_family_clients: BothClients,
    generic_device_schema: GenericSchemaAPI,
    client_type: str,
    case: QueryShapeCase,
) -> None:
    query = await _generate_query(generic_family_clients, client_type, generic_device_schema, case.kwargs)

    assert query == _query("TestGenericDevice", case.expected_node)


@dataclass
class DefaultQueryCase:
    name: str
    kind: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)


DEFAULT_QUERY_CASES = [
    DefaultQueryCase(
        name="location-default",
        kind="BuiltinLocation",
        expected={
            "BuiltinLocation": {
                "count": None,
                "edges": {
                    "node": {
                        "id": None,
                        "hfid": None,
                        "display_label": None,
                        "__typename": None,
                        "name": {"value": None},
                        "description": {"value": None},
                        "type": {"value": None},
                        "primary_tag": {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}},
                    }
                },
                "@filters": {},
            }
        },
    ),
    DefaultQueryCase(
        name="location-include",
        kind="BuiltinLocation",
        kwargs={"include": ["tags"]},
        expected={
            "BuiltinLocation": {
                "count": None,
                "edges": {
                    "node": {
                        "id": None,
                        "hfid": None,
                        "display_label": None,
                        "__typename": None,
                        "name": {"value": None},
                        "description": {"value": None},
                        "type": {"value": None},
                        "tags": {
                            "edges": {
                                "node": {
                                    "id": None,
                                    "hfid": None,
                                    "display_label": None,
                                    "__typename": None,
                                    "name": {"value": None},
                                    "description": {"value": None},
                                }
                            }
                        },
                        "primary_tag": {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}},
                    }
                },
                "@filters": {},
            }
        },
    ),
    DefaultQueryCase(
        name="location-exclude",
        kind="BuiltinLocation",
        kwargs={"exclude": ["description"]},
        expected={
            "BuiltinLocation": {
                "count": None,
                "edges": {
                    "node": {
                        "id": None,
                        "hfid": None,
                        "display_label": None,
                        "__typename": None,
                        "name": {"value": None},
                        "type": {"value": None},
                        "primary_tag": {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}},
                    }
                },
                "@filters": {},
            }
        },
    ),
    DefaultQueryCase(
        name="location-include-and-exclude",
        kind="BuiltinLocation",
        kwargs={"include": ["tags"], "exclude": ["description"]},
        expected={
            "BuiltinLocation": {
                "count": None,
                "edges": {
                    "node": {
                        "id": None,
                        "hfid": None,
                        "display_label": None,
                        "__typename": None,
                        "name": {"value": None},
                        "type": {"value": None},
                        "tags": {
                            "edges": {
                                "node": {
                                    "id": None,
                                    "hfid": None,
                                    "display_label": None,
                                    "__typename": None,
                                    "name": {"value": None},
                                    "description": {"value": None},
                                }
                            }
                        },
                        "primary_tag": {"node": {"id": None, "hfid": None, "display_label": None, "__typename": None}},
                    }
                },
                "@filters": {},
            }
        },
    ),
    DefaultQueryCase(
        name="tag-default",
        kind="BuiltinTag",
        expected={
            "BuiltinTag": {
                "count": None,
                "edges": {
                    "node": {
                        "id": None,
                        "hfid": None,
                        "display_label": None,
                        "__typename": None,
                        "name": {"value": None},
                        "description": {"value": None},
                    }
                },
                "@filters": {},
            }
        },
    ),
    DefaultQueryCase(
        name="tag-include",
        kind="BuiltinTag",
        kwargs={"include": ["tags"]},
        expected={
            "BuiltinTag": {
                "count": None,
                "edges": {
                    "node": {
                        "id": None,
                        "hfid": None,
                        "display_label": None,
                        "__typename": None,
                        "name": {"value": None},
                        "description": {"value": None},
                    }
                },
                "@filters": {},
            }
        },
    ),
    DefaultQueryCase(
        name="tag-exclude",
        kind="BuiltinTag",
        kwargs={"exclude": ["description"]},
        expected={
            "BuiltinTag": {
                "count": None,
                "edges": {
                    "node": {
                        "id": None,
                        "hfid": None,
                        "display_label": None,
                        "__typename": None,
                        "name": {"value": None},
                    }
                },
                "@filters": {},
            }
        },
    ),
    DefaultQueryCase(
        name="tag-include-and-exclude",
        kind="BuiltinTag",
        kwargs={"include": ["tags"], "exclude": ["description"]},
        expected={
            "BuiltinTag": {
                "count": None,
                "edges": {
                    "node": {
                        "id": None,
                        "hfid": None,
                        "display_label": None,
                        "__typename": None,
                        "name": {"value": None},
                    }
                },
                "@filters": {},
            }
        },
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in DEFAULT_QUERY_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_default_query_is_unchanged(
    generic_family_clients: BothClients,
    location_schema: NodeSchemaAPI,
    tag_schema: NodeSchemaAPI,
    client_type: str,
    case: DefaultQueryCase,
) -> None:
    schema = {"BuiltinLocation": location_schema, "BuiltinTag": tag_schema}[case.kind]

    query = await _generate_query(generic_family_clients, client_type, schema, case.kwargs)

    assert query == case.expected


@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_is_unchanged_when_schema_grows(
    generic_family_clients: BothClients, tag_schema: NodeSchemaAPI, client_type: str
) -> None:
    extended_data = tag_schema.model_dump()
    extended_data["attributes"] += [
        {"name": "color", "kind": "Text", "optional": True},
        {"name": "priority", "kind": "Number", "optional": True},
    ]
    extended_data["relationships"] += [
        {"name": "primary_location", "peer": "BuiltinLocation", "cardinality": "one", "optional": True},
    ]
    extended_schema = NodeSchemaAPI.model_validate(extended_data)

    before = await _generate_query(generic_family_clients, client_type, tag_schema, {"only": ["name"]})
    after = await _generate_query(generic_family_clients, client_type, extended_schema, {"only": ["name"]})
    extended_default = await _generate_query(generic_family_clients, client_type, extended_schema)

    assert after == before
    assert {"color", "priority", "primary_location"} <= extended_default["BuiltinTag"]["edges"]["node"].keys()


LOCATION_ID = "5d2c0f96-3b7e-4f0a-9a63-1f1d2a6b7c01"
TAG_ID = "8a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
QUERY_METHODS = ["filters", "all", "get"]


async def _query_nodes(
    clients: BothClients, client_type: str, method: str, kind: str, **kwargs: object
) -> list[InfrahubNode] | list[InfrahubNodeSync]:
    """Call ``filters``, ``all`` or ``get`` on one client and return the nodes as a list."""
    if method == "get":
        kwargs.setdefault("id", LOCATION_ID)
    client = clients.standard if client_type == "standard" else clients.sync
    result = getattr(client, method)(kind=kind, **kwargs)
    if client_type == "standard":
        result = await result
    return result if isinstance(result, list) else [result]


@dataclass
class ConflictCase:
    name: str
    kwargs: dict[str, Any]
    parameters: list[str]


CONFLICT_CASES = [
    ConflictCase(name="include", kwargs={"include": ["tags"]}, parameters=["only", "include"]),
    ConflictCase(name="empty-include", kwargs={"include": []}, parameters=["only", "include"]),
    ConflictCase(name="exclude", kwargs={"exclude": ["description"]}, parameters=["only", "exclude"]),
    ConflictCase(name="empty-exclude", kwargs={"exclude": []}, parameters=["only", "exclude"]),
    ConflictCase(
        name="include-and-exclude",
        kwargs={"include": ["tags"], "exclude": []},
        parameters=["only", "include", "exclude"],
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in CONFLICT_CASES])
@pytest.mark.parametrize("method", QUERY_METHODS)
@pytest.mark.parametrize("client_type", client_types)
async def test_only_with_include_or_exclude_is_rejected_before_any_request(
    httpx_mock: HTTPXMock, clients: BothClients, client_type: str, method: str, case: ConflictCase
) -> None:
    # No schema is cached, so even resolving the kind would send a request.
    with pytest.raises(SelectionConflictError, match="'only' cannot be combined with") as exc:
        await _query_nodes(clients, client_type, method, "BuiltinLocation", only=["name"], **case.kwargs)

    assert exc.value.parameters == case.parameters
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("method", QUERY_METHODS)
@pytest.mark.parametrize("client_type", client_types)
async def test_only_with_unknown_name_is_rejected_before_the_data_query(
    httpx_mock: HTTPXMock, generic_family_clients: BothClients, client_type: str, method: str
) -> None:
    with pytest.raises(
        SelectionFieldNotFoundError, match=re.escape("'serial' is not an attribute or relationship of BuiltinLocation.")
    ) as exc:
        await _query_nodes(generic_family_clients, client_type, method, "BuiltinLocation", only=["name", "serial"])

    assert (exc.value.kind, exc.value.field, exc.value.implementing_kinds) == ("BuiltinLocation", "serial", [])
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("method", QUERY_METHODS)
@pytest.mark.parametrize("client_type", client_types)
async def test_only_with_implementing_kind_name_needs_fragment(
    httpx_mock: HTTPXMock, generic_family_clients: BothClients, client_type: str, method: str
) -> None:
    with pytest.raises(SelectionFieldNotFoundError, match=re.escape("(TestRouter). Pass fragment=True")) as exc:
        await _query_nodes(generic_family_clients, client_type, method, "TestGenericDevice", only=["name", "role"])

    assert (exc.value.kind, exc.value.field, exc.value.implementing_kinds) == (
        "TestGenericDevice",
        "role",
        ["TestRouter"],
    )
    assert httpx_mock.get_requests() == []


def _location_response(node: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"BuiltinLocation": {"count": 1, "edges": [{"node": node}]}}}


LOCATION_FLOOR_DATA: dict[str, Any] = {"id": LOCATION_ID, "display_label": "dfw1", "__typename": "BuiltinLocation"}
TAG_FLOOR_DATA: dict[str, Any] = {"id": TAG_ID, "hfid": ["red"], "display_label": "red", "__typename": "BuiltinTag"}


@pytest.mark.parametrize("method", QUERY_METHODS)
@pytest.mark.parametrize("client_type", client_types)
async def test_nodes_from_only_raise_on_unfetched_reads(
    httpx_mock: HTTPXMock, generic_family_clients: BothClients, client_type: str, method: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_location_response({**LOCATION_FLOOR_DATA, "name": {"value": "dfw1"}}),
    )

    nodes = await _query_nodes(generic_family_clients, client_type, method, "BuiltinLocation", only=["name"])

    assert [node.name.value for node in nodes] == ["dfw1"]
    node = nodes[0]
    for field_name, read, advice in (
        ("description", lambda: node.description.value, "Add it to the selection before reading it."),
        ("primary_tag", lambda: node.primary_tag.id, "Add it to the selection before reading it."),
        ("tags", lambda: node.tags.peers, "Add it to the selection, or call fetch() on it, before reading it."),
    ):
        message = f"BuiltinLocation.{field_name} was not fetched (selection: only=['name']). {advice}"
        with pytest.raises(FieldNotLoadedError, match=f"^{re.escape(message)}$") as exc:
            read()
        assert (exc.value.kind, exc.value.field, exc.value.selection) == (
            "BuiltinLocation",
            field_name,
            "only=['name']",
        )


@pytest.mark.parametrize("client_type", client_types)
async def test_only_reference_peer_is_not_stored_and_points_at_hydration(
    httpx_mock: HTTPXMock, generic_family_clients: BothClients, client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_location_response({**LOCATION_FLOOR_DATA, "primary_tag": {"node": TAG_FLOOR_DATA}}),
    )
    client = generic_family_clients.standard if client_type == "standard" else generic_family_clients.sync

    nodes = await _query_nodes(generic_family_clients, client_type, "filters", "BuiltinLocation", only=["primary_tag"])

    node = nodes[0]
    assert (node.primary_tag.id, node.primary_tag.typename) == (TAG_ID, "BuiltinTag")
    assert client.store.get(key=LOCATION_ID, raise_when_missing=False) is node
    assert client.store.get(key=TAG_ID, raise_when_missing=False) is None
    hint = (
        f"Unable to find the node '{TAG_ID}' in the store (main): the peer of relationship 'primary_tag' "
        "is not in the client store (it was not fetched, or the store was not populated). "
        "Call fetch() on the relationship, or query with prefetch_relationships=True."
    )
    with pytest.raises(NodeNotFoundError, match=re.escape(hint)) as exc:
        _ = node.primary_tag.peer
    assert exc.value.message == hint
    assert (exc.value.identifier, exc.value.node_type) == ({"key": [TAG_ID]}, "BuiltinTag")


@pytest.mark.parametrize("client_type", client_types)
async def test_reference_peer_of_another_kind_in_the_store_keeps_its_error(
    httpx_mock: HTTPXMock, generic_family_clients: BothClients, location_schema: NodeSchemaAPI, client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_location_response({**LOCATION_FLOOR_DATA, "primary_tag": {"node": TAG_FLOOR_DATA}}),
    )
    nodes = await _query_nodes(generic_family_clients, client_type, "filters", "BuiltinLocation", only=["primary_tag"])
    other_data = {"id": TAG_ID, "name": {"value": "not-a-tag"}, "type": {"value": "site"}}
    if client_type == "standard":
        generic_family_clients.standard.store.set(
            node=InfrahubNode(client=generic_family_clients.standard, schema=location_schema, data=other_data)
        )
    else:
        generic_family_clients.sync.store.set(
            node=InfrahubNodeSync(client=generic_family_clients.sync, schema=location_schema, data=other_data)
        )

    with pytest.raises(NodeInvalidError, match="Found a node of a different kind instead of BuiltinTag") as exc:
        _ = nodes[0].primary_tag.peer
    assert "prefetch_relationships" not in str(exc.value)


@pytest.fixture
async def tag_with_locations_schema(tag_schema: NodeSchemaAPI) -> NodeSchemaAPI:
    data = tag_schema.model_dump()
    data["relationships"] = [
        {"name": "locations", "peer": "BuiltinLocation", "cardinality": "many", "optional": True},
    ]
    return NodeSchemaAPI.model_validate(data)


@pytest.fixture
async def prefetch_clients(
    clients: BothClients, location_schema: NodeSchemaAPI, tag_with_locations_schema: NodeSchemaAPI
) -> BothClients:
    cache_data = {"version": "1.0", "nodes": [location_schema.model_dump(), tag_with_locations_schema.model_dump()]}
    clients.standard.schema.set_cache(cache_data)
    clients.sync.schema.set_cache(cache_data)
    return clients


@pytest.mark.parametrize("client_type", client_types)
async def test_only_with_prefetch_stores_the_peer_with_a_strict_peer_selection(
    httpx_mock: HTTPXMock, prefetch_clients: BothClients, client_type: str
) -> None:
    tag_data = {**TAG_FLOOR_DATA, "name": {"value": "red"}, "description": {"value": "Red tag"}}
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_location_response({**LOCATION_FLOOR_DATA, "primary_tag": {"node": tag_data}}),
    )
    client = prefetch_clients.standard if client_type == "standard" else prefetch_clients.sync

    nodes = await _query_nodes(
        prefetch_clients, client_type, "filters", "BuiltinLocation", only=["primary_tag"], prefetch_relationships=True
    )

    stored_tag = client.store.get(key=TAG_ID)
    assert (stored_tag.name.value, stored_tag.description.value) == ("red", "Red tag")
    assert nodes[0].primary_tag.peer is stored_tag
    selection = "peer of BuiltinLocation.primary_tag, fetched with only=['primary_tag']"
    with pytest.raises(
        FieldNotLoadedError, match=re.escape(f"BuiltinTag.locations was not fetched (selection: {selection})")
    ) as exc:
        _ = stored_tag.locations.peers
    assert (exc.value.kind, exc.value.field, exc.value.selection) == ("BuiltinTag", "locations", selection)


@dataclass
class NonStrictSelectionCase:
    name: str
    kwargs: dict[str, Any]
    label: str


NON_STRICT_SELECTION_CASES = [
    NonStrictSelectionCase(name="default", kwargs={}, label="default selection"),
    NonStrictSelectionCase(name="exclude", kwargs={"exclude": ["description"]}, label="exclude=['description']"),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in NON_STRICT_SELECTION_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_nodes_without_only_warn_naming_their_selection(
    httpx_mock: HTTPXMock, generic_family_clients: BothClients, client_type: str, case: NonStrictSelectionCase
) -> None:
    location_data = {**LOCATION_FLOOR_DATA, "hfid": ["dfw1"], "name": {"value": "dfw1"}, "type": {"value": "site"}}
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=_location_response(location_data))

    nodes = await _query_nodes(generic_family_clients, client_type, "filters", "BuiltinLocation", **case.kwargs)

    message = (
        f"BuiltinLocation.tags was not fetched (selection: {case.label}). "
        "Add it to the selection, or call fetch() on it, before reading it. "
        "This will raise FieldNotLoadedError in infrahub-sdk 2.0."
    )
    with pytest.warns(FieldNotLoadedWarning, match=f"^{re.escape(message)}$"):
        assert nodes[0].tags.peers == []


BLUE_TAG_ID = "9b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e"
BLUE_TAG_DATA: dict[str, Any] = {
    "id": BLUE_TAG_ID,
    "hfid": ["blue"],
    "display_label": "blue",
    "__typename": "BuiltinTag",
    "name": {"value": "blue"},
    "description": {"value": None},
}
LOCATION_ATTRIBUTES: dict[str, Any] = {
    "hfid": ["dfw1"],
    "name": {"value": "dfw1"},
    "description": {"value": None},
    "type": {"value": "site"},
}


@dataclass
class ExpandedPeerCase:
    name: str
    kwargs: dict[str, Any]
    location_data: dict[str, Any]
    peer_id: str
    label: str


EXPANDED_PEER_CASES = [
    ExpandedPeerCase(
        name="include",
        kwargs={"include": ["tags"]},
        location_data={
            **LOCATION_FLOOR_DATA,
            **LOCATION_ATTRIBUTES,
            "primary_tag": {"node": TAG_FLOOR_DATA},
            "tags": {"count": 1, "edges": [{"node": BLUE_TAG_DATA}]},
        },
        peer_id=BLUE_TAG_ID,
        label="peer of BuiltinLocation.tags, fetched with include=['tags']",
    ),
    ExpandedPeerCase(
        name="prefetch-relationships",
        kwargs={"prefetch_relationships": True},
        location_data={**LOCATION_FLOOR_DATA, **LOCATION_ATTRIBUTES, "primary_tag": {"node": BLUE_TAG_DATA}},
        peer_id=BLUE_TAG_ID,
        label="peer of BuiltinLocation.primary_tag, fetched with default selection",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in EXPANDED_PEER_CASES])
@pytest.mark.parametrize("client_type", client_types)
async def test_peer_expanded_without_only_warns_on_unknown_reads(
    httpx_mock: HTTPXMock, prefetch_clients: BothClients, client_type: str, case: ExpandedPeerCase
) -> None:
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=_location_response(case.location_data))
    client = prefetch_clients.standard if client_type == "standard" else prefetch_clients.sync

    await _query_nodes(prefetch_clients, client_type, "filters", "BuiltinLocation", **case.kwargs)

    peer = client.store.get(key=case.peer_id)
    assert peer.name.value == "blue"
    message = (
        f"BuiltinTag.locations was not fetched (selection: {case.label}). "
        "Add it to the selection, or call fetch() on it, before reading it. "
        "This will raise FieldNotLoadedError in infrahub-sdk 2.0."
    )
    with pytest.warns(FieldNotLoadedWarning, match=f"^{re.escape(message)}$") as record:
        assert peer.locations.peers == []
    assert [str(item.message) for item in record] == [message]


@pytest.mark.parametrize("client_type", client_types)
async def test_identity_only_peer_points_at_the_relationship_it_came_from(
    httpx_mock: HTTPXMock, prefetch_clients: BothClients, client_type: str
) -> None:
    location_data = EXPANDED_PEER_CASES[0].location_data
    httpx_mock.add_response(method="POST", url="http://mock/graphql/main", json=_location_response(location_data))
    client = prefetch_clients.standard if client_type == "standard" else prefetch_clients.sync

    nodes = await _query_nodes(prefetch_clients, client_type, "filters", "BuiltinLocation", include=["tags"])

    # include expands tags only, so the primary_tag peer is built from its identity fields alone.
    primary_tag = client.store.get(key=TAG_ID)
    assert nodes[0].primary_tag.peer is primary_tag
    assert (primary_tag.id, primary_tag.display_label) == (TAG_ID, "red")
    message = (
        "BuiltinTag.name was not fetched: this node only carries its identity fields "
        "(peer of BuiltinLocation.primary_tag). Call fetch() on BuiltinLocation.primary_tag, "
        "or query with prefetch_relationships=True, before reading it. "
        "This will raise FieldNotLoadedError in infrahub-sdk 2.0."
    )
    with pytest.warns(FieldNotLoadedWarning, match=f"^{re.escape(message)}$") as record:
        assert primary_tag.name.value is None
    assert [str(item.message) for item in record] == [message]


@pytest.mark.parametrize("client_type", client_types)
async def test_saving_a_node_from_only_sends_only_its_id_and_the_modified_attribute(
    httpx_mock: HTTPXMock, generic_family_clients: BothClients, client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json=_location_response({**LOCATION_FLOOR_DATA, "name": {"value": "dfw1"}}),
        match_headers={"X-Infrahub-Tracker": "query-builtinlocation-page1"},
    )
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {"BuiltinLocationUpdate": {"ok": True, "object": {"id": LOCATION_ID}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-builtinlocation-update"},
    )
    nodes = await _query_nodes(generic_family_clients, client_type, "filters", "BuiltinLocation", only=["name"])
    node = nodes[0]

    with no_field_warning():
        attribute_of(node, "name").value = "dfw2"
        if isinstance(node, InfrahubNode):
            await node.save()
        else:
            node.save()

    requests = httpx_mock.get_requests()
    assert [request.headers["X-Infrahub-Tracker"] for request in requests] == [
        "query-builtinlocation-page1",
        "mutation-builtinlocation-update",
    ]
    assert mutation_input(requests[1]) == {"name": {"value": "dfw2"}, "id": LOCATION_ID}
