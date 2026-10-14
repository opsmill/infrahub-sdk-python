from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import FieldNotFoundError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.types import Order

if TYPE_CHECKING:
    from infrahub_sdk.schema import NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

REFERENCE: dict[str, Any] = {"id": None, "hfid": None, "display_label": None, "__typename": None}
VALUE: dict[str, Any] = {"value": None}
OBJECT: dict[str, Any] = {"id": None, "display_label": None, "__typename": None}
ATTRIBUTE_PROPERTIES: dict[str, Any] = {
    "value": None,
    "is_default": None,
    "is_from_profile": None,
    "is_protected": None,
    "updated_at": None,
    "source": OBJECT,
    "owner": OBJECT,
}
RELATIONSHIP_PROPERTIES: dict[str, Any] = {"is_protected": None, "updated_at": None, "source": OBJECT, "owner": OBJECT}
ATTRIBUTE_METADATA: dict[str, Any] = {"value": None, "updated_at": None, "updated_by": OBJECT}
NODE_METADATA: dict[str, Any] = {"created_at": None, "created_by": OBJECT, "updated_at": None, "updated_by": OBJECT}
RELATIONSHIP_METADATA: dict[str, Any] = {"updated_at": None, "updated_by": OBJECT}

LOCATION_DEFAULT_FIELDS: dict[str, Any] = {
    "name": VALUE,
    "description": VALUE,
    "type": VALUE,
    "primary_tag": {"node": REFERENCE},
}
TAG_DEFAULT_FIELDS: dict[str, Any] = {"name": VALUE, "description": VALUE}
PERSON_DEFAULT_FIELDS: dict[str, Any] = {"name": VALUE, "height": VALUE}

TAG = {
    "name": "Tag",
    "namespace": "Builtin",
    "default_filter": "name__value",
    "attributes": [
        {"name": "name", "kind": "Text", "unique": True},
        {"name": "description", "kind": "Text", "optional": True},
    ],
}
ANIMAL_ATTRIBUTES = [{"name": "name", "kind": "Text"}, {"name": "weight", "kind": "Number", "optional": True}]
ANIMAL_RELATIONSHIPS = [
    {"name": "owner", "peer": "TestingPerson", "cardinality": "one", "identifier": "person__animal"},
    {"name": "best_friend", "peer": "TestingPerson", "cardinality": "one", "optional": True},
]
HIERARCHY_RELATIONSHIPS = [
    {"name": "parent", "peer": "LocationGeneric", "cardinality": "one", "kind": "Hierarchy", "optional": True},
    {"name": "children", "peer": "LocationGeneric", "cardinality": "many", "kind": "Hierarchy", "optional": True},
]


def schema_payload(rack: NodeSchemaAPI, location: NodeSchemaAPI, grown: bool = False) -> dict[str, Any]:
    """The schemas of the tests, as the schema endpoint returns them.

    With `grown`, the rack, the animal generic (and the kinds that inherit its fields) and the dog
    each gain an attribute and a relationship that no test names in `only`.
    """
    rack_data = rack.model_dump()
    animal_attributes = list(ANIMAL_ATTRIBUTES)
    animal_relationships = list(ANIMAL_RELATIONSHIPS)
    dog_attributes = [{"name": "breed", "kind": "Text"}]
    dog_relationships = [{"name": "walker", "peer": "TestingPerson", "cardinality": "one", "optional": True}]
    if grown:
        rack_data["attributes"].append({"name": "serial", "kind": "Text", "optional": True})
        rack_data["relationships"].append({"name": "owner", "peer": "TestingPerson", "cardinality": "one"})
        animal_attributes.append({"name": "nickname", "kind": "Text", "optional": True})
        animal_relationships.append({"name": "vet", "peer": "TestingPerson", "cardinality": "one", "optional": True})
        dog_attributes.append({"name": "pattern", "kind": "Text", "optional": True})
        dog_relationships.append({"name": "rival", "peer": "TestingPerson", "cardinality": "one", "optional": True})

    return {
        "version": "1.0",
        "generics": [
            {
                "name": "Animal",
                "namespace": "Testing",
                "human_friendly_id": ["owner__name__value", "name__value"],
                "used_by": ["TestingCat", "TestingDog"],
                "attributes": animal_attributes,
                "relationships": animal_relationships,
            },
            {
                "name": "Generic",
                "namespace": "Location",
                "hierarchical": True,
                "used_by": ["LocationSite"],
                "attributes": [{"name": "name", "kind": "Text"}],
                "relationships": HIERARCHY_RELATIONSHIPS,
            },
            {
                "name": "Place",
                "namespace": "Infra",
                "used_by": ["LocationSite"],
                "attributes": [{"name": "name", "kind": "Text"}],
            },
        ],
        "nodes": [
            rack_data,
            location.model_dump(),
            TAG,
            {
                "name": "Person",
                "namespace": "Testing",
                "human_friendly_id": ["name__value"],
                "attributes": [
                    {"name": "name", "kind": "Text"},
                    {"name": "height", "kind": "Number", "optional": True},
                ],
                "relationships": [
                    {"name": "animals", "peer": "TestingAnimal", "cardinality": "many", "identifier": "person__animal"}
                ],
            },
            {
                "name": "Cat",
                "namespace": "Testing",
                "inherit_from": ["TestingAnimal"],
                "human_friendly_id": ["owner__name__value", "name__value", "color__value"],
                "attributes": [
                    *animal_attributes,
                    {"name": "breed", "kind": "Text"},
                    {"name": "color", "kind": "Color", "optional": True},
                ],
                "relationships": animal_relationships,
            },
            {
                "name": "Dog",
                "namespace": "Testing",
                "inherit_from": ["TestingAnimal"],
                "human_friendly_id": ["owner__name__value", "name__value"],
                "attributes": [*animal_attributes, *dog_attributes],
                "relationships": [*animal_relationships, *dog_relationships],
            },
            {
                "name": "Site",
                "namespace": "Location",
                "inherit_from": ["LocationGeneric", "InfraPlace"],
                "hierarchy": "LocationGeneric",
                "attributes": [
                    {"name": "name", "kind": "Text"},
                    {"name": "facility", "kind": "Text", "optional": True},
                ],
                "relationships": HIERARCHY_RELATIONSHIPS,
            },
        ],
    }


@pytest.fixture
async def query_clients(clients: BothClients, schema_with_hfid: dict[str, NodeSchemaAPI]) -> BothClients:
    payload = schema_payload(rack=schema_with_hfid["rack"], location=schema_with_hfid["location"])
    clients.standard.schema.set_cache(payload)
    clients.sync.schema.set_cache(payload)
    return clients


def expected_query(
    kind: str,
    node_fields: dict[str, Any],
    filters: dict[str, Any] | None = None,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """The whole query: the queried node always gets `id`, `display_label` and `__typename`, never `hfid`."""
    edges: dict[str, Any] = {"node": {"id": None, "display_label": None, "__typename": None, **node_fields}}
    if include_metadata:
        edges["node_metadata"] = NODE_METADATA
    return {kind: {"count": None, "@filters": filters or {}, "edges": edges}}


def one(peer_fields: dict[str, Any] | None = None, **edge: dict[str, Any]) -> dict[str, Any]:
    return {"node": {**REFERENCE, **(peer_fields or {})}, **edge}


def many(peer_fields: dict[str, Any] | None = None, **edge: dict[str, Any]) -> dict[str, Any]:
    return {"edges": {"node": {**REFERENCE, **(peer_fields or {})}, **edge}}


def hierarchy_one(peer_fields: dict[str, Any] | None = None, **edge: dict[str, Any]) -> dict[str, Any]:
    return {"node": {"...on LocationGeneric": {**REFERENCE, **(peer_fields or {})}}, **edge}


def hierarchy_many(peer_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"edges": {"node": {"...on LocationGeneric": {**REFERENCE, **(peer_fields or {})}}}}


def aliased(kind: str, name: str, field_data: dict[str, Any]) -> dict[str, Any]:
    return {"@alias": f"__alias__{kind}__{name}", **field_data}


async def generate_only_query(
    clients: BothClients,
    client_type: str,
    kind: str,
    only: list[str],
    filters: dict[str, Any] | None = None,
    offset: int | str | None = None,
    limit: int | str | None = None,
    fragment: bool = False,
    prefetch_relationships: bool = False,
    partial_match: bool = False,
    property: bool = False,
    order: Order | None = None,
    include_metadata: bool = False,
) -> dict[str, Any]:
    if client_type == "standard":
        schema = await clients.standard.schema.get(kind=kind)
        node = InfrahubNode(client=clients.standard, schema=schema)
        return await node._generate_only_query_data(
            only=only,
            filters=filters,
            offset=offset,
            limit=limit,
            fragment=fragment,
            prefetch_relationships=prefetch_relationships,
            partial_match=partial_match,
            property=property,
            order=order,
            include_metadata=include_metadata,
        )
    schema = clients.sync.schema.get(kind=kind)
    node_sync = InfrahubNodeSync(client=clients.sync, schema=schema)
    return node_sync._generate_only_query_data(
        only=only,
        filters=filters,
        offset=offset,
        limit=limit,
        fragment=fragment,
        prefetch_relationships=prefetch_relationships,
        partial_match=partial_match,
        property=property,
        order=order,
        include_metadata=include_metadata,
    )


async def generate_default_query(
    clients: BothClients,
    client_type: str,
    kind: str,
    filters: dict[str, Any] | None = None,
    offset: int | str | None = None,
    limit: int | str | None = None,
    include: list[str] | None = None,
    fragment: bool = False,
    partial_match: bool = False,
    order: Order | None = None,
) -> dict[str, Any]:
    if client_type == "standard":
        schema = await clients.standard.schema.get(kind=kind)
        return await InfrahubNode(client=clients.standard, schema=schema).generate_query_data(
            filters=filters,
            offset=offset,
            limit=limit,
            include=include,
            fragment=fragment,
            partial_match=partial_match,
            order=order,
        )
    schema = clients.sync.schema.get(kind=kind)
    return InfrahubNodeSync(client=clients.sync, schema=schema).generate_query_data(
        filters=filters,
        offset=offset,
        limit=limit,
        include=include,
        fragment=fragment,
        partial_match=partial_match,
        order=order,
    )


@dataclass
class OnlyQueryCase:
    name: str
    kind: str
    only: list[str]
    expected: dict[str, Any]
    prefetch_relationships: bool = False
    fragment: bool = False
    property: bool = False
    include_metadata: bool = False


ONLY_QUERY_CASES = [
    OnlyQueryCase(
        name="one-attribute",
        kind="BuiltinLocation",
        only=["name"],
        expected=expected_query("BuiltinLocation", {"name": VALUE}),
    ),
    OnlyQueryCase(name="empty", kind="BuiltinLocation", only=[], expected=expected_query("BuiltinLocation", {})),
    OnlyQueryCase(
        name="id-and-display-label",
        kind="BuiltinLocation",
        only=["id", "display_label"],
        expected=expected_query("BuiltinLocation", {}),
    ),
    OnlyQueryCase(
        name="duplicate-names",
        kind="BuiltinLocation",
        only=["name", "id", "name"],
        expected=expected_query("BuiltinLocation", {"name": VALUE}),
    ),
    OnlyQueryCase(
        name="relationships-as-references",
        kind="BuiltinRack",
        only=["location", "tags", "member_of_groups"],
        expected=expected_query("BuiltinRack", {"location": one(), "tags": many(), "member_of_groups": many()}),
    ),
    OnlyQueryCase(
        name="prefetch-cardinality-one",
        kind="BuiltinRack",
        only=["location"],
        prefetch_relationships=True,
        expected=expected_query("BuiltinRack", {"location": one(LOCATION_DEFAULT_FIELDS)}),
    ),
    OnlyQueryCase(
        name="prefetch-only-named-relationships",
        kind="BuiltinRack",
        only=["facility_id", "tags"],
        prefetch_relationships=True,
        expected=expected_query("BuiltinRack", {"facility_id": VALUE, "tags": many(TAG_DEFAULT_FIELDS)}),
    ),
    OnlyQueryCase(
        name="parent-as-reference",
        kind="LocationSite",
        only=["parent"],
        expected=expected_query("LocationSite", {"parent": hierarchy_one()}),
    ),
    OnlyQueryCase(
        name="children-ancestors-descendants-as-references",
        kind="LocationSite",
        only=["children", "ancestors", "descendants"],
        expected=expected_query(
            "LocationSite",
            {"children": hierarchy_many(), "ancestors": hierarchy_many(), "descendants": hierarchy_many()},
        ),
    ),
    OnlyQueryCase(
        name="hierarchy-fields-with-prefetch",
        kind="LocationSite",
        only=["parent", "descendants"],
        prefetch_relationships=True,
        expected=expected_query(
            "LocationSite",
            {"parent": hierarchy_one({"name": VALUE}), "descendants": hierarchy_many({"name": VALUE})},
        ),
    ),
    OnlyQueryCase(
        name="prefetch-adds-no-unnamed-hierarchy-field",
        kind="LocationSite",
        only=["name"],
        prefetch_relationships=True,
        expected=expected_query("LocationSite", {"name": VALUE}),
    ),
    OnlyQueryCase(
        name="hierarchy-fields-on-hierarchical-generic",
        kind="LocationGeneric",
        only=["name", "children"],
        expected=expected_query("LocationGeneric", {"name": VALUE, "children": hierarchy_many()}),
    ),
    OnlyQueryCase(
        name="hierarchy-field-only-on-implementing-kind",
        kind="InfraPlace",
        only=["parent"],
        expected=expected_query(
            "InfraPlace", {"...on LocationSite": {"parent": aliased("LocationSite", "parent", hierarchy_one())}}
        ),
    ),
    OnlyQueryCase(
        name="hfid-through-attribute",
        kind="BuiltinLocation",
        only=["hfid"],
        expected=expected_query("BuiltinLocation", {"name": VALUE}),
    ),
    OnlyQueryCase(
        name="hfid-through-relationship",
        kind="BuiltinRack",
        only=["hfid"],
        expected=expected_query("BuiltinRack", {"facility_id": VALUE, "location": one({"name": VALUE})}),
    ),
    OnlyQueryCase(
        name="hfid-merged-with-named-relationship",
        kind="BuiltinRack",
        only=["location", "description", "hfid"],
        expected=expected_query(
            "BuiltinRack", {"facility_id": VALUE, "description": VALUE, "location": one({"name": VALUE})}
        ),
    ),
    OnlyQueryCase(
        name="hfid-merged-with-prefetch",
        kind="BuiltinRack",
        only=["hfid"],
        prefetch_relationships=True,
        expected=expected_query("BuiltinRack", {"facility_id": VALUE, "location": one(LOCATION_DEFAULT_FIELDS)}),
    ),
    OnlyQueryCase(
        name="hfid-on-kind-without-hfid", kind="BuiltinTag", only=["hfid"], expected=expected_query("BuiltinTag", {})
    ),
    OnlyQueryCase(
        name="generic-name-on-generic",
        kind="TestingAnimal",
        only=["name", "owner"],
        expected=expected_query("TestingAnimal", {"name": VALUE, "owner": one()}),
    ),
    OnlyQueryCase(
        name="generic-name-on-one-implementing-kind",
        kind="TestingAnimal",
        only=["color", "walker"],
        expected=expected_query(
            "TestingAnimal",
            {
                "...on TestingCat": {"color": aliased("TestingCat", "color", VALUE)},
                "...on TestingDog": {"walker": aliased("TestingDog", "walker", one())},
            },
        ),
    ),
    OnlyQueryCase(
        name="generic-name-on-every-implementing-kind",
        kind="TestingAnimal",
        only=["breed"],
        expected=expected_query(
            "TestingAnimal",
            {
                "...on TestingCat": {"breed": aliased("TestingCat", "breed", VALUE)},
                "...on TestingDog": {"breed": aliased("TestingDog", "breed", VALUE)},
            },
        ),
    ),
    OnlyQueryCase(
        name="generic-implementing-kind-relationship-with-prefetch",
        kind="TestingAnimal",
        only=["walker"],
        prefetch_relationships=True,
        expected=expected_query(
            "TestingAnimal",
            {"...on TestingDog": {"walker": aliased("TestingDog", "walker", one(PERSON_DEFAULT_FIELDS))}},
        ),
    ),
    OnlyQueryCase(
        name="generic-hfid-per-implementing-kind",
        kind="TestingAnimal",
        only=["hfid"],
        expected=expected_query(
            "TestingAnimal",
            {
                "name": VALUE,
                "owner": one({"name": VALUE}),
                "...on TestingCat": {"color": aliased("TestingCat", "color", VALUE)},
            },
        ),
    ),
    OnlyQueryCase(
        name="generic-hfid-merged-with-named-relationship",
        kind="TestingAnimal",
        only=["owner", "hfid"],
        expected=expected_query(
            "TestingAnimal",
            {
                "name": VALUE,
                "owner": one({"name": VALUE}),
                "...on TestingCat": {"color": aliased("TestingCat", "color", VALUE)},
            },
        ),
    ),
    OnlyQueryCase(
        name="generic-fragment-adds-nothing",
        kind="TestingAnimal",
        only=["name", "color"],
        fragment=True,
        expected=expected_query(
            "TestingAnimal", {"name": VALUE, "...on TestingCat": {"color": aliased("TestingCat", "color", VALUE)}}
        ),
    ),
    OnlyQueryCase(
        name="property-on-named-fields",
        kind="BuiltinRack",
        only=["description", "location"],
        property=True,
        expected=expected_query(
            "BuiltinRack",
            {"description": ATTRIBUTE_PROPERTIES, "location": one(properties=RELATIONSHIP_PROPERTIES)},
        ),
    ),
    OnlyQueryCase(
        name="property-on-hfid-fields",
        kind="BuiltinRack",
        only=["hfid"],
        property=True,
        expected=expected_query(
            "BuiltinRack",
            {
                "facility_id": ATTRIBUTE_PROPERTIES,
                "location": one({"name": ATTRIBUTE_PROPERTIES}, properties=RELATIONSHIP_PROPERTIES),
            },
        ),
    ),
    OnlyQueryCase(
        name="property-on-hierarchy-field",
        kind="LocationSite",
        only=["parent"],
        property=True,
        expected=expected_query("LocationSite", {"parent": hierarchy_one(properties=RELATIONSHIP_PROPERTIES)}),
    ),
    OnlyQueryCase(
        name="metadata-on-named-fields",
        kind="BuiltinRack",
        only=["description", "location"],
        include_metadata=True,
        expected=expected_query(
            "BuiltinRack",
            {
                "description": ATTRIBUTE_METADATA,
                "location": one(node_metadata=NODE_METADATA, relationship_metadata=RELATIONSHIP_METADATA),
            },
            include_metadata=True,
        ),
    ),
    OnlyQueryCase(
        name="metadata-not-on-hierarchy-field",
        kind="LocationSite",
        only=["parent"],
        include_metadata=True,
        expected=expected_query("LocationSite", {"parent": hierarchy_one()}, include_metadata=True),
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in ONLY_QUERY_CASES])
async def test_only_query(query_clients: BothClients, client_type: str, case: OnlyQueryCase) -> None:
    data = await generate_only_query(
        query_clients,
        client_type,
        kind=case.kind,
        only=case.only,
        fragment=case.fragment,
        prefetch_relationships=case.prefetch_relationships,
        property=case.property,
        include_metadata=case.include_metadata,
    )

    assert data == case.expected


@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_hierarchy_prefetch_matches_default_hierarchy_fields(
    query_clients: BothClients, client_type: str
) -> None:
    hierarchy_names = ["parent", "children", "ancestors", "descendants"]
    data = await generate_only_query(
        query_clients, client_type, kind="LocationSite", only=hierarchy_names, prefetch_relationships=True
    )
    default = await generate_default_query(query_clients, client_type, kind="LocationSite", include=hierarchy_names)

    only_node = data["LocationSite"]["edges"]["node"]
    default_node = default["LocationSite"]["edges"]["node"]
    assert {name: only_node[name] for name in hierarchy_names} == {name: default_node[name] for name in hierarchy_names}
    assert only_node["parent"] == hierarchy_one({"name": VALUE})


@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_arguments(query_clients: BothClients, client_type: str) -> None:
    arguments: dict[str, Any] = {
        "filters": {"facility_id__value": "R1"},
        "offset": "$offset",
        "limit": "$limit",
        "partial_match": True,
        "order": Order(disable=True),
    }

    data = await generate_only_query(query_clients, client_type, kind="BuiltinRack", only=["facility_id"], **arguments)
    default = await generate_default_query(query_clients, client_type, kind="BuiltinRack", **arguments)

    assert data == expected_query(
        "BuiltinRack",
        {"facility_id": VALUE},
        filters={
            "facility_id__value": "R1",
            "order": Order(disable=True),
            "offset": "$offset",
            "limit": "$limit",
            "partial_match": True,
        },
    )
    assert data["BuiltinRack"]["@filters"] == default["BuiltinRack"]["@filters"]
    assert data["BuiltinRack"]["count"] == default["BuiltinRack"]["count"]


@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_rejects_unknown_name(query_clients: BothClients, client_type: str) -> None:
    with pytest.raises(
        FieldNotFoundError, match=re.escape("'nmae' is not an attribute or relationship of BuiltinRack.")
    ):
        await generate_only_query(query_clients, client_type, kind="BuiltinRack", only=["facility_id", "nmae"])


@dataclass
class SchemaGrowthCase:
    name: str
    kind: str
    only: list[str]
    expected: dict[str, Any]


SCHEMA_GROWTH_CASES = [
    SchemaGrowthCase(
        name="node-kind",
        kind="BuiltinRack",
        only=["description", "tags", "hfid"],
        expected=expected_query(
            "BuiltinRack",
            {"facility_id": VALUE, "description": VALUE, "location": one({"name": VALUE}), "tags": many()},
        ),
    ),
    SchemaGrowthCase(
        name="generic-kind-and-implementing-kinds",
        kind="TestingAnimal",
        only=["weight", "breed", "walker", "hfid"],
        expected=expected_query(
            "TestingAnimal",
            {
                "name": VALUE,
                "weight": VALUE,
                "owner": one({"name": VALUE}),
                "...on TestingCat": {
                    "breed": aliased("TestingCat", "breed", VALUE),
                    "color": aliased("TestingCat", "color", VALUE),
                },
                "...on TestingDog": {
                    "breed": aliased("TestingDog", "breed", VALUE),
                    "walker": aliased("TestingDog", "walker", one()),
                },
            },
        ),
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in SCHEMA_GROWTH_CASES])
async def test_only_query_unchanged_when_schema_grows(
    query_clients: BothClients,
    schema_with_hfid: dict[str, NodeSchemaAPI],
    client_type: str,
    case: SchemaGrowthCase,
) -> None:
    before = await generate_only_query(query_clients, client_type, kind=case.kind, only=case.only)
    default_before = await generate_default_query(query_clients, client_type, kind=case.kind, fragment=True)

    grown = schema_payload(rack=schema_with_hfid["rack"], location=schema_with_hfid["location"], grown=True)
    query_clients.standard.schema.set_cache(grown)
    query_clients.sync.schema.set_cache(grown)

    after = await generate_only_query(query_clients, client_type, kind=case.kind, only=case.only)
    default_after = await generate_default_query(query_clients, client_type, kind=case.kind, fragment=True)

    assert default_after != default_before
    assert before == case.expected
    assert after == case.expected
