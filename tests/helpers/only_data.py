"""Schema, mocked responses and client helpers shared by the unit tests of queries with `only`."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from infrahub_sdk.graphql import Query

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk import InfrahubClient, InfrahubClientSync
    from tests.unit.sdk.conftest import BothClients

DEVICE_ID = "a5f1d5a0-5f5c-4a2b-9a4c-3e1c4c1f0d01"
SITE_ID = "b6e2c6b1-6a6d-4b3c-8b5d-4f2d5d2e1e01"
TAG_ID = "c7d3b7c2-7b7e-4c4d-9c6e-5a3e6e3f2f01"
TAG_2_ID = "c7d3b7c2-7b7e-4c4d-9c6e-5a3e6e3f2f02"
CAT_ID = "d8c4a8d3-8c8f-4d5e-8d7f-6b4f7f4a3a01"
DOG_ID = "d8c4a8d3-8c8f-4d5e-8d7f-6b4f7f4a3a02"
REGION_ID = "f1a6e1f5-1e1b-4f7a-8f9b-8d6b9b6c5c01"
PARENT_ID = "f1a6e1f5-1e1b-4f7a-8f9b-8d6b9b6c5c02"

HIERARCHY_RELATIONSHIPS = [
    {"name": "parent", "peer": "LocationGeneric", "cardinality": "one", "kind": "Hierarchy", "optional": True},
    {"name": "children", "peer": "LocationGeneric", "cardinality": "many", "kind": "Hierarchy", "optional": True},
]
OWNER_RELATIONSHIP = {"name": "owner", "peer": "TestingPerson", "cardinality": "one", "optional": True}

SCHEMA: dict[str, Any] = {
    "version": "1.0",
    "generics": [
        {
            "name": "Animal",
            "namespace": "Testing",
            "human_friendly_id": ["owner__name__value", "name__value"],
            "used_by": ["TestingCat", "TestingDog"],
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": [OWNER_RELATIONSHIP],
        },
        {
            "name": "Generic",
            "namespace": "Location",
            "hierarchical": True,
            "used_by": ["LocationRegion"],
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": HIERARCHY_RELATIONSHIPS,
        },
    ],
    "nodes": [
        {
            "name": "Site",
            "namespace": "Infra",
            "human_friendly_id": ["name__value"],
            "attributes": [
                {"name": "name", "kind": "Text", "unique": True},
                {"name": "description", "kind": "Text", "optional": True},
            ],
        },
        {
            "name": "Tag",
            "namespace": "Builtin",
            "human_friendly_id": ["name__value"],
            "attributes": [{"name": "name", "kind": "Text", "unique": True}],
        },
        {
            "name": "Device",
            "namespace": "Infra",
            "human_friendly_id": ["name__value", "site__name__value"],
            "attributes": [
                {"name": "name", "kind": "Text"},
                {"name": "description", "kind": "Text", "optional": True},
            ],
            "relationships": [
                {"name": "site", "peer": "InfraSite", "cardinality": "one"},
                {"name": "tags", "peer": "BuiltinTag", "cardinality": "many", "optional": True},
            ],
        },
        {
            "name": "Person",
            "namespace": "Testing",
            "human_friendly_id": ["name__value"],
            "attributes": [{"name": "name", "kind": "Text"}],
        },
        {
            "name": "Cat",
            "namespace": "Testing",
            "inherit_from": ["TestingAnimal"],
            "human_friendly_id": ["home__name__value", "name__value"],
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": [
                OWNER_RELATIONSHIP,
                {"name": "home", "peer": "InfraSite", "cardinality": "one", "optional": True},
            ],
        },
        {
            "name": "Dog",
            "namespace": "Testing",
            "inherit_from": ["TestingAnimal"],
            "human_friendly_id": ["owner__name__value", "name__value"],
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": [
                OWNER_RELATIONSHIP,
                {"name": "walker", "peer": "TestingPerson", "cardinality": "one", "optional": True},
            ],
        },
        {
            "name": "Region",
            "namespace": "Location",
            "inherit_from": ["LocationGeneric"],
            "hierarchy": "LocationGeneric",
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": HIERARCHY_RELATIONSHIPS,
        },
        {
            "name": "Shelter",
            "namespace": "Testing",
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": [{"name": "animals", "peer": "TestingAnimal", "cardinality": "many", "optional": True}],
        },
        {
            "name": "Contract",
            "namespace": "Network",
            "inherit_from": ["CoreFileObject"],
            "attributes": [
                {"name": "file_name", "kind": "Text", "read_only": True},
                {"name": "checksum", "kind": "Text", "read_only": True},
            ],
        },
    ],
}

REFERENCE: dict[str, Any] = {"id": None, "hfid": None, "display_label": None, "__typename": None}
VALUE: dict[str, Any] = {"value": None}
PAGINATION = {"offset": "$offset", "limit": "$limit"}


def expected_body(
    kind: str, query_name: str, node_fields: dict[str, Any], filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The JSON body of the first page request: the node always gets `id`, `display_label` and `__typename`."""
    query = {
        kind: {
            "count": None,
            "edges": {"node": {"id": None, "display_label": None, "__typename": None, **node_fields}},
            "@filters": {**(filters or {}), **PAGINATION},
        }
    }
    return {
        "query": Query(query=query, name=query_name, variables={"offset": int, "limit": int}).render(),
        "variables": {"offset": 0, "limit": 3},
        "operationName": query_name,
    }


def peer(id: str, typename: str, **fields: dict[str, Any]) -> dict[str, Any]:
    return {"node": {"id": id, "hfid": None, "display_label": None, "__typename": typename, **fields}}


def peers(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"edges": list(nodes)}


def node_data(id: str, typename: str, **fields: dict[str, Any]) -> dict[str, Any]:
    return {"node": {"id": id, "display_label": None, "__typename": typename, **fields}}


DEVICE_WITH_HFID = node_data(
    DEVICE_ID, "InfraDevice", name={"value": "dev1"}, site=peer(SITE_ID, "InfraSite", name={"value": "Paris"})
)


def add_page(httpx_mock: HTTPXMock, kind: str, edges: list[dict[str, Any]]) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {kind: {"count": len(edges), "edges": edges}}},
        match_headers={"X-Infrahub-Tracker": f"query-{kind.lower()}-page1"},
    )


def client_of(clients: BothClients, client_type: str) -> InfrahubClient | InfrahubClientSync:
    return clients.standard if client_type == "standard" else clients.sync


async def run(clients: BothClients, client_type: str, method: str, **kwargs: object) -> object:
    if client_type == "standard":
        return await getattr(clients.standard, method)(**kwargs)
    return getattr(clients.sync, method)(**kwargs)


async def query_nodes(clients: BothClients, client_type: str, method: str, **kwargs: object) -> list[Any]:
    """Run a query method on one of the clients and return the nodes it returned as a list."""
    result = await run(clients, client_type, method, **kwargs)
    return result if isinstance(result, list) else [result]


async def resolve(result: object) -> object:
    """Await what a call on the async client returns; a call on the sync client has already run."""
    if inspect.isawaitable(result):
        return await result
    return result
