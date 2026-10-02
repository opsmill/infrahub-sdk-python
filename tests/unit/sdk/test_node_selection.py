"""Tests for the fields a node query selects, including exclusive selection with ``only``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.schema import GenericSchemaAPI, NodeSchema, NodeSchemaAPI

if TYPE_CHECKING:
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
