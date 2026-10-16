from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import FieldNotFoundError
from infrahub_sdk.graphql import Query
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync
from infrahub_sdk.node._only import (  # noqa: PLC2701  # the helpers under test are private to the package
    OnlyMarker,
    only_query_fields,
)
from infrahub_sdk.schema import GenericSchemaAPI
from infrahub_sdk.types import Order
from tests.helpers import only_data

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

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
    each gain an attribute and a relationship that no test names in `only`, and the location and the
    person, whose names are parts of HFIDs, each gain an attribute.
    """
    rack_data = rack.model_dump()
    location_data = location.model_dump()
    person_attributes = [{"name": "name", "kind": "Text"}, {"name": "height", "kind": "Number", "optional": True}]
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
        location_data["attributes"].append({"name": "latitude", "kind": "Number", "optional": True})
        person_attributes.append({"name": "age", "kind": "Number", "optional": True})

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
            location_data,
            TAG,
            {
                "name": "Person",
                "namespace": "Testing",
                "human_friendly_id": ["name__value"],
                "attributes": person_attributes,
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
    hfid: bool = False,
) -> dict[str, Any]:
    """The whole query: the queried node always gets `id`, `display_label` and `__typename`, and `hfid` with `hfid`."""
    identifiers: dict[str, Any] = {"id": None, "hfid": None} if hfid else {"id": None}
    edges: dict[str, Any] = {"node": {**identifiers, "display_label": None, "__typename": None, **node_fields}}
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
    prefetch_relationships: bool = False,
    partial_match: bool = False,
    property: bool = False,
    order: Order | None = None,
    include_metadata: bool = False,
) -> dict[str, Any]:
    if client_type == "standard":
        schema = await clients.standard.schema.get(kind=kind)
        implementing_schemas = (
            [await clients.standard.schema.get(kind=name) for name in schema.used_by]
            if isinstance(schema, GenericSchemaAPI)
            else []
        )
        node = InfrahubNode(client=clients.standard, schema=schema)
        return await node._generate_only_query_data(
            fields=only_query_fields(only=only, schema=schema, implementing_schemas=implementing_schemas),
            filters=filters,
            offset=offset,
            limit=limit,
            prefetch_relationships=prefetch_relationships,
            partial_match=partial_match,
            property=property,
            order=order,
            include_metadata=include_metadata,
        )
    schema = clients.sync.schema.get(kind=kind)
    implementing_schemas = (
        [clients.sync.schema.get(kind=name) for name in schema.used_by] if isinstance(schema, GenericSchemaAPI) else []
    )
    node_sync = InfrahubNodeSync(client=clients.sync, schema=schema)
    return node_sync._generate_only_query_data(
        fields=only_query_fields(only=only, schema=schema, implementing_schemas=implementing_schemas),
        filters=filters,
        offset=offset,
        limit=limit,
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
        name="hfid-on-kind-whose-hfid-reads-an-attribute",
        kind="BuiltinLocation",
        only=["hfid"],
        expected=expected_query("BuiltinLocation", {}, hfid=True),
    ),
    OnlyQueryCase(
        name="hfid-on-kind-whose-hfid-reads-a-relationship",
        kind="BuiltinRack",
        only=["hfid"],
        expected=expected_query("BuiltinRack", {}, hfid=True),
    ),
    OnlyQueryCase(
        name="hfid-merged-with-named-fields",
        kind="BuiltinRack",
        only=["location", "description", "hfid"],
        expected=expected_query("BuiltinRack", {"description": VALUE, "location": one()}, hfid=True),
    ),
    OnlyQueryCase(
        name="hfid-with-prefetch",
        kind="BuiltinRack",
        only=["tags", "hfid"],
        prefetch_relationships=True,
        expected=expected_query("BuiltinRack", {"tags": many(TAG_DEFAULT_FIELDS)}, hfid=True),
    ),
    OnlyQueryCase(
        name="hfid-with-prefetch-of-a-relationship-the-hfid-reads",
        kind="BuiltinRack",
        only=["location", "hfid"],
        prefetch_relationships=True,
        expected=expected_query("BuiltinRack", {"location": one(LOCATION_DEFAULT_FIELDS)}, hfid=True),
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
        name="generic-hfid",
        kind="TestingAnimal",
        only=["hfid"],
        expected=expected_query("TestingAnimal", {}, hfid=True),
    ),
    OnlyQueryCase(
        name="generic-hfid-merged-with-named-fields",
        kind="TestingAnimal",
        only=["owner", "color", "hfid"],
        expected=expected_query(
            "TestingAnimal",
            {"owner": one(), "...on TestingCat": {"color": aliased("TestingCat", "color", VALUE)}},
            hfid=True,
        ),
    ),
    OnlyQueryCase(
        name="generic-hfid-with-prefetch",
        kind="TestingAnimal",
        only=["owner", "hfid"],
        prefetch_relationships=True,
        expected=expected_query("TestingAnimal", {"owner": one(PERSON_DEFAULT_FIELDS)}, hfid=True),
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
        name="property-adds-nothing-to-hfid",
        kind="BuiltinRack",
        only=["description", "hfid"],
        property=True,
        expected=expected_query("BuiltinRack", {"description": ATTRIBUTE_PROPERTIES}, hfid=True),
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
        prefetch_relationships=case.prefetch_relationships,
        property=case.property,
        include_metadata=case.include_metadata,
    )

    assert data == case.expected


@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_hierarchy_prefetch_matches_default_when_the_generic_is_the_declared_peer(
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


def declared_parent_schema(parent_peer: str) -> dict[str, Any]:
    """A site whose HFID reads `code`, which only the region has, through a `parent` that declares `parent_peer`.

    The region has its own `parent` and `children`, which a prefetch of the site's parent must not request.
    """
    return {
        "version": "1.0",
        "generics": [
            {
                "name": "Generic",
                "namespace": "Location",
                "hierarchical": True,
                "used_by": ["LocationRegion", "LocationSite"],
                "attributes": [{"name": "name", "kind": "Text"}],
            }
        ],
        "nodes": [
            {
                "name": "Region",
                "namespace": "Location",
                "inherit_from": ["LocationGeneric"],
                "hierarchy": "LocationGeneric",
                "attributes": [{"name": "name", "kind": "Text"}, {"name": "code", "kind": "Text"}],
                "relationships": [
                    {
                        "name": "parent",
                        "peer": "LocationGeneric",
                        "cardinality": "one",
                        "kind": "Hierarchy",
                        "optional": True,
                    },
                    {
                        "name": "children",
                        "peer": "LocationSite",
                        "cardinality": "many",
                        "kind": "Hierarchy",
                        "optional": True,
                    },
                ],
            },
            {
                "name": "Site",
                "namespace": "Location",
                "inherit_from": ["LocationGeneric"],
                "hierarchy": "LocationGeneric",
                "human_friendly_id": ["parent__code__value", "name__value"],
                "attributes": [{"name": "name", "kind": "Text"}],
                "relationships": [
                    {"name": "parent", "peer": parent_peer, "cardinality": "one", "kind": "Hierarchy", "optional": True}
                ],
            },
        ],
    }


@pytest.mark.parametrize("client_type", client_types)
async def test_only_query_prefetch_uses_the_declared_parent_kind(clients: BothClients, client_type: str) -> None:
    schema = declared_parent_schema(parent_peer="LocationRegion")
    clients.standard.schema.set_cache(schema)
    clients.sync.schema.set_cache(schema)

    data = await generate_only_query(
        clients, client_type, kind="LocationSite", only=["parent"], prefetch_relationships=True
    )

    assert data == expected_query(
        "LocationSite",
        {"parent": {"node": {"...on LocationRegion": {**REFERENCE, "name": VALUE, "code": VALUE}}}},
    )


@pytest.mark.parametrize("client_type", client_types)
async def test_prefetched_parent_of_the_declared_kind_is_built_and_stored(
    clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    schema = declared_parent_schema(parent_peer="LocationRegion")
    clients.standard.schema.set_cache(schema)
    clients.sync.schema.set_cache(schema)
    region_data = only_data.peer(only_data.REGION_ID, "LocationRegion", name={"value": "Europe"}, code={"value": "EU"})
    only_data.add_page(
        httpx_mock,
        "LocationSite",
        [only_data.node_data(only_data.SITE_ID, "LocationSite", name={"value": "Lyon"}, parent=region_data)],
    )

    [site] = await only_data.query_nodes(
        clients, client_type, "all", kind="LocationSite", only=["name", "parent"], prefetch_relationships=True
    )

    region = only_data.client_of(clients, client_type).store.get(key=only_data.REGION_ID, kind="LocationRegion")
    assert [region.get_kind(), region._get_attribute("code").value, region._only_marker] == [
        "LocationRegion",
        "EU",
        OnlyMarker(only=("name", "parent"), peer_of="LocationSite.parent"),
    ]
    assert site.hfid == ["EU", "Lyon"]


def place_schema(site_hfid: list[str] | None) -> dict[str, Any]:
    """A generic without an HFID, implemented by a site whose HFID is `site_hfid`."""
    return {
        "version": "1.0",
        "generics": [
            {
                "name": "Place",
                "namespace": "Infra",
                "used_by": ["InfraSite"],
                "attributes": [{"name": "name", "kind": "Text"}],
            }
        ],
        "nodes": [
            {
                "name": "Site",
                "namespace": "Infra",
                "inherit_from": ["InfraPlace"],
                "human_friendly_id": site_hfid,
                "attributes": [{"name": "name", "kind": "Text"}],
            }
        ],
    }


@dataclass
class GenericHfidCase:
    name: str
    site_hfid: list[str] | None
    expected: dict[str, Any]


GENERIC_HFID_CASES = [
    GenericHfidCase(
        name="implementing-kind-with-hfid",
        site_hfid=["name__value"],
        expected=expected_query("InfraPlace", {}, hfid=True),
    ),
    GenericHfidCase(name="no-kind-with-hfid", site_hfid=None, expected=expected_query("InfraPlace", {})),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in GENERIC_HFID_CASES])
async def test_only_query_hfid_on_a_generic_without_hfid_follows_its_implementing_kinds(
    clients: BothClients, client_type: str, case: GenericHfidCase
) -> None:
    schema = place_schema(site_hfid=case.site_hfid)
    clients.standard.schema.set_cache(schema)
    clients.sync.schema.set_cache(schema)

    data = await generate_only_query(clients, client_type, kind="InfraPlace", only=["hfid"])

    assert data == case.expected


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
async def test_only_query_text_does_not_depend_on_name_order(query_clients: BothClients, client_type: str) -> None:
    names = ["breed", "walker", "hfid", "weight", "color"]
    forward = await generate_only_query(query_clients, client_type, kind="TestingAnimal", only=names)
    backward = await generate_only_query(query_clients, client_type, kind="TestingAnimal", only=names[::-1])

    assert Query(query=backward, name="Animals").render() == Query(query=forward, name="Animals").render()


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
    grown_kind: str
    prefetch_relationships: bool = False


SCHEMA_GROWTH_CASES = [
    SchemaGrowthCase(
        name="node-kind",
        kind="BuiltinRack",
        only=["description", "tags", "hfid"],
        expected=expected_query("BuiltinRack", {"description": VALUE, "tags": many()}, hfid=True),
        grown_kind="BuiltinRack",
    ),
    SchemaGrowthCase(
        name="peer-kind-the-hfid-reads-with-prefetch",
        kind="BuiltinRack",
        only=["facility_id", "hfid"],
        prefetch_relationships=True,
        expected=expected_query("BuiltinRack", {"facility_id": VALUE}, hfid=True),
        grown_kind="BuiltinLocation",
    ),
    SchemaGrowthCase(
        name="generic-peer-kind-the-hfid-reads-with-prefetch",
        kind="TestingAnimal",
        only=["hfid"],
        prefetch_relationships=True,
        expected=expected_query("TestingAnimal", {}, hfid=True),
        grown_kind="TestingPerson",
    ),
    SchemaGrowthCase(
        name="generic-kind-and-implementing-kinds",
        kind="TestingAnimal",
        only=["weight", "breed", "walker", "hfid"],
        expected=expected_query(
            "TestingAnimal",
            {
                "weight": VALUE,
                "...on TestingCat": {"breed": aliased("TestingCat", "breed", VALUE)},
                "...on TestingDog": {
                    "breed": aliased("TestingDog", "breed", VALUE),
                    "walker": aliased("TestingDog", "walker", one()),
                },
            },
            hfid=True,
        ),
        grown_kind="TestingAnimal",
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
    before = await generate_only_query(
        query_clients,
        client_type,
        kind=case.kind,
        only=case.only,
        prefetch_relationships=case.prefetch_relationships,
    )
    default_before = await generate_default_query(query_clients, client_type, kind=case.grown_kind, fragment=True)

    grown = schema_payload(rack=schema_with_hfid["rack"], location=schema_with_hfid["location"], grown=True)
    query_clients.standard.schema.set_cache(grown)
    query_clients.sync.schema.set_cache(grown)

    after = await generate_only_query(
        query_clients,
        client_type,
        kind=case.kind,
        only=case.only,
        prefetch_relationships=case.prefetch_relationships,
    )
    default_after = await generate_default_query(query_clients, client_type, kind=case.grown_kind, fragment=True)

    assert default_after != default_before
    assert before == case.expected
    assert after == case.expected
