from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import Error, FieldNotFoundError, FieldNotLoadedError
from infrahub_sdk.graphql import Query
from infrahub_sdk.node._only import OnlyMarker  # noqa: PLC2701  # the marker is private to the package
from infrahub_sdk.types import Order

from . import test_client_only as only_data
from .test_node_only_access import resolve

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from .conftest import BothClients

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

client_types = ["standard", "sync"]

DEVICE = "InfraDevice"
SITE = "InfraSite"
TAG = "BuiltinTag"
REGION = "LocationRegion"
CAT = "TestingCat"
DOG = "TestingDog"
SHELTER = "TestingShelter"
SHELTER_ID = "a7c9e1b3-2d4f-4a6b-8c0d-1e2f3a4b5c01"
REGION_PEER_ID = "f1a6e1f5-1e1b-4f7a-8f9b-8d6b9b6c5c09"

SCHEMA: dict[str, Any] = {
    **only_data.SCHEMA,
    "nodes": [
        *only_data.SCHEMA["nodes"],
        {
            "name": "Shelter",
            "namespace": "Testing",
            "attributes": [{"name": "name", "kind": "Text"}],
            "relationships": [{"name": "animals", "peer": "TestingAnimal", "cardinality": "many", "optional": True}],
        },
    ],
}

NODE_FIELDS = {"id": None, "hfid": None, "display_label": None, "__typename": None}
PEER_ORDER = Order(disable=True)


@pytest.fixture
def only_clients(clients: BothClients) -> BothClients:
    clients.standard.schema.set_cache(SCHEMA)
    clients.sync.schema.set_cache(SCHEMA)
    return clients


def reference(id: str, typename: str, hfid: list[str]) -> dict[str, Any]:
    """A peer as the server returns it in a reference, with the HFID the server calculated."""
    return {"node": {"id": id, "hfid": hfid, "display_label": hfid[0], "__typename": typename}}


def add_counts(httpx_mock: HTTPXMock, counts: dict[str, int]) -> None:
    """Answer the count queries of a parallel filters call, which carry no tracker header.

    Register it after every tracked response, so a tracked request never takes it.
    """
    httpx_mock.add_response(
        method="POST",
        url="http://mock/graphql/main",
        json={"data": {kind: {"count": count} for kind, count in counts.items()}},
    )


def request_bodies(httpx_mock: HTTPXMock) -> list[dict[str, Any]]:
    return [json.loads(request.content) for request in httpx_mock.get_requests()]


def body_of(httpx_mock: HTTPXMock, operation: str) -> dict[str, Any]:
    bodies = [body for body in request_bodies(httpx_mock) if body["operationName"] == operation]
    assert len(bodies) == 1
    return bodies[0]


def default_body(
    kind: str, query_name: str, node_fields: dict[str, Any], filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The JSON body of the first page request of a query without `only`, which also requests `hfid`."""
    query = {
        kind: {
            "count": None,
            "edges": {"node": {**NODE_FIELDS, **node_fields}},
            "@filters": {**(filters or {}), **only_data.PAGINATION},
        }
    }
    return {
        "query": Query(query=query, name=query_name, variables={"offset": int, "limit": int}).render(),
        "variables": {"offset": 0, "limit": 3},
        "operationName": query_name,
    }


async def query_all(
    clients: BothClients,
    client_type: str,
    httpx_mock: HTTPXMock,
    kind: str,
    edge: dict[str, Any],
    only: list[str] | None,
) -> list[Any]:
    """Return the nodes that `all(kind, only=...)` builds from a response holding `edge`."""
    only_data.add_page(httpx_mock, kind, [edge])
    return await only_data.query_nodes(clients, client_type, "all", kind=kind, only=only)


def not_fetched(kind: str, field: str, only: list[str]) -> str:
    return re.escape(f"{kind}.{field} was not fetched: the node was queried with only={only!r}.")


DEVICE_WITH_SITE = only_data.node_data(only_data.DEVICE_ID, DEVICE, site=reference(only_data.SITE_ID, SITE, ["Paris"]))
SHELTER_WITH_ANIMALS = only_data.node_data(
    SHELTER_ID,
    SHELTER,
    animals=only_data.peers(only_data.peer(only_data.CAT_ID, CAT), only_data.peer(only_data.DOG_ID, DOG)),
)


@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_fetch_with_only_requests_the_named_fields(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    [device] = await query_all(only_clients, client_type, httpx_mock, kind=DEVICE, edge=DEVICE_WITH_SITE, only=["site"])
    only_data.add_page(httpx_mock, SITE, [only_data.node_data(only_data.SITE_ID, SITE, name={"value": "Paris"})])
    client = only_data.client_of(only_clients, client_type)

    await resolve(device.site.fetch(only=["name"]))

    assert request_bodies(httpx_mock)[1:] == [
        only_data.expected_body(SITE, "Get_InfraSite", {"name": only_data.VALUE}, filters={"ids": [only_data.SITE_ID]})
    ]
    site = device.site.peer
    assert [site.name.value, site._only_marker] == ["Paris", OnlyMarker(only=("name",))]
    assert client.store.get(key=only_data.SITE_ID, kind=SITE) is site
    with pytest.raises(FieldNotLoadedError, match=not_fetched(SITE, "description", ["name"])):
        _ = site.description.value


@dataclass
class FetchedHfidCase:
    name: str
    fetch_only: list[str] | None
    fetched_fields: dict[str, Any]
    expected_hfid: list[str] | None
    expected_hfid_str: str | None


FETCHED_HFID_CASES = [
    FetchedHfidCase(
        name="hfid-fields-not-fetched-keeps-the-reference-hfid",
        fetch_only=["description"],
        fetched_fields={"description": {"value": "Main site"}},
        expected_hfid=["Paris"],
        expected_hfid_str="InfraSite__Paris",
    ),
    FetchedHfidCase(
        name="hfid-fields-fetched-gives-the-calculated-hfid",
        fetch_only=["name"],
        fetched_fields={"name": {"value": "Lyon"}},
        expected_hfid=["Lyon"],
        expected_hfid_str="InfraSite__Lyon",
    ),
    FetchedHfidCase(
        name="peer-fetched-without-only-keeps-the-calculated-hfid",
        fetch_only=None,
        fetched_fields={"description": {"value": "Main site"}},
        expected_hfid=None,
        expected_hfid_str=None,
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in FETCHED_HFID_CASES])
async def test_related_node_hfid_after_fetch(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: FetchedHfidCase
) -> None:
    [device] = await query_all(only_clients, client_type, httpx_mock, kind=DEVICE, edge=DEVICE_WITH_SITE, only=["site"])
    only_data.add_page(httpx_mock, SITE, [only_data.node_data(only_data.SITE_ID, SITE, **case.fetched_fields)])

    await resolve(device.site.fetch(only=case.fetch_only))

    site = device.site
    assert [site.hfid, site.hfid_str, site.initialized] == [case.expected_hfid, case.expected_hfid_str, True]


@dataclass
class NotLoadedFetchCase:
    name: str
    device_only: list[str] | None
    error: type[Error]
    message: str


NOT_LOADED_FETCH_CASES = [
    NotLoadedFetchCase(
        name="node-from-only",
        device_only=["name"],
        error=FieldNotLoadedError,
        message=not_fetched(DEVICE, "site", ["name"]),
    ),
    NotLoadedFetchCase(
        name="default-node",
        device_only=None,
        error=Error,
        message="Unable to fetch the peer, id and/or typename are not defined",
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in NOT_LOADED_FETCH_CASES])
async def test_related_node_fetch_with_only_on_relationship_not_loaded_raises(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: NotLoadedFetchCase
) -> None:
    edge = only_data.node_data(only_data.DEVICE_ID, DEVICE, name={"value": "dev1"})
    [device] = await query_all(only_clients, client_type, httpx_mock, kind=DEVICE, edge=edge, only=case.device_only)

    with pytest.raises(Error, match=case.message) as error:
        await resolve(device.site.fetch(only=["name"]))

    assert type(error.value) is case.error
    assert len(httpx_mock.get_requests()) == 1


@dataclass
class PeerKindCase:
    name: str
    fetch_only: list[str]
    message: str
    shelter_only: list[str]


PEER_KIND_CASES = [
    PeerKindCase(
        name="name-missing-on-first-peer-kind",
        fetch_only=["walker"],
        message="'walker' is not an attribute or relationship of TestingCat",
        shelter_only=["animals"],
    ),
    PeerKindCase(
        name="name-missing-on-second-peer-kind",
        fetch_only=["name", "home"],
        message="'home' is not an attribute or relationship of TestingDog",
        shelter_only=["animals"],
    ),
    PeerKindCase(
        name="relationship-reloaded-first",
        fetch_only=["walker"],
        message="'walker' is not an attribute or relationship of TestingCat",
        shelter_only=["name"],
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in PEER_KIND_CASES])
async def test_manager_fetch_with_name_missing_on_one_peer_kind_sends_no_peer_query(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: PeerKindCase
) -> None:
    [shelter] = await query_all(
        only_clients, client_type, httpx_mock, kind=SHELTER, edge=SHELTER_WITH_ANIMALS, only=case.shelter_only
    )
    reloads = [] if shelter.animals.is_loaded else [SHELTER_WITH_ANIMALS]
    if reloads:
        only_data.add_page(httpx_mock, SHELTER, reloads)

    with pytest.raises(FieldNotFoundError, match=case.message):
        await resolve(shelter.animals.fetch(only=case.fetch_only))

    expected_operations = ["All_TestingShelter"] + ["Get_TestingShelter"] * len(reloads)
    assert [body["operationName"] for body in request_bodies(httpx_mock)] == expected_operations


@dataclass
class MisspeltNameCase:
    name: str
    kind: str
    edge: dict[str, Any]
    relationship: str
    message: str


MISSPELT_NAME_CASES = [
    MisspeltNameCase(
        name="node-peer-kind",
        kind=DEVICE,
        edge=only_data.node_data(only_data.DEVICE_ID, DEVICE, name={"value": "dev1"}),
        relationship="tags",
        message="'nmae' is not an attribute or relationship of BuiltinTag",
    ),
    MisspeltNameCase(
        name="generic-peer-kind",
        kind=SHELTER,
        edge=only_data.node_data(SHELTER_ID, SHELTER, name={"value": "North"}),
        relationship="animals",
        message="'nmae' is not an attribute or relationship of TestingAnimal",
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in MISSPELT_NAME_CASES])
async def test_manager_fetch_with_misspelt_name_on_relationship_not_loaded_sends_no_request(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: MisspeltNameCase
) -> None:
    [node] = await query_all(only_clients, client_type, httpx_mock, kind=case.kind, edge=case.edge, only=["name"])
    manager = getattr(node, case.relationship)

    with pytest.raises(FieldNotFoundError, match=case.message):
        await resolve(manager.fetch(only=["nmae"]))

    assert manager.is_loaded is False
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize("client_type", client_types)
async def test_manager_fetch_reloads_relationship_of_node_from_only(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    edge = only_data.node_data(only_data.DEVICE_ID, DEVICE, name={"value": "dev1"})
    [device] = await query_all(only_clients, client_type, httpx_mock, kind=DEVICE, edge=edge, only=["name"])
    only_data.add_page(
        httpx_mock,
        DEVICE,
        [
            only_data.node_data(
                only_data.DEVICE_ID,
                DEVICE,
                tags=only_data.peers(only_data.peer(only_data.TAG_ID, TAG), only_data.peer(only_data.TAG_2_ID, TAG)),
            )
        ],
    )
    only_data.add_page(
        httpx_mock,
        TAG,
        [
            only_data.node_data(only_data.TAG_ID, TAG, name={"value": "red"}),
            only_data.node_data(only_data.TAG_2_ID, TAG, name={"value": "blue"}),
        ],
    )
    add_counts(httpx_mock, {TAG: 2})
    client = only_data.client_of(only_clients, client_type)

    await resolve(device.tags.fetch(only=["name"]))

    assert [body["operationName"] for body in request_bodies(httpx_mock)] == [
        "All_InfraDevice",
        "Get_InfraDevice",
        "Count_BuiltinTag",
        "Filters_BuiltinTag",
    ]
    assert body_of(httpx_mock, "Get_InfraDevice") == only_data.expected_body(
        DEVICE,
        "Get_InfraDevice",
        {"tags": {"edges": {"node": only_data.REFERENCE}}},
        filters={"ids": [only_data.DEVICE_ID]},
    )
    assert body_of(httpx_mock, "Filters_BuiltinTag") == only_data.expected_body(
        TAG,
        "Filters_BuiltinTag",
        {"name": only_data.VALUE},
        filters={"ids": [only_data.TAG_ID, only_data.TAG_2_ID], "order": PEER_ORDER},
    )
    assert client.store.get(key=only_data.DEVICE_ID, kind=DEVICE) is device
    assert [device.tags.is_loaded, device.tags.peer_ids] == [True, [only_data.TAG_ID, only_data.TAG_2_ID]]
    stored_tags = [client.store.get(key=id, kind=TAG) for id in (only_data.TAG_ID, only_data.TAG_2_ID)]
    assert [(tag._get_attribute("name").value, tag._only_marker) for tag in stored_tags] == [
        ("red", OnlyMarker(only=("name",))),
        ("blue", OnlyMarker(only=("name",))),
    ]


@dataclass
class HierarchyFetchCase:
    name: str
    relationship: str


HIERARCHY_FETCH_CASES = [
    HierarchyFetchCase(name="ancestors", relationship="ancestors"),
    HierarchyFetchCase(name="descendants", relationship="descendants"),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in HIERARCHY_FETCH_CASES])
async def test_hierarchy_manager_fetch_with_only_loads_peers_of_node_from_only(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: HierarchyFetchCase
) -> None:
    edge = only_data.node_data(only_data.REGION_ID, REGION, name={"value": "Europe"})
    [region] = await query_all(only_clients, client_type, httpx_mock, kind=REGION, edge=edge, only=["name"])
    only_data.add_page(
        httpx_mock,
        REGION,
        [
            only_data.node_data(
                only_data.REGION_ID,
                REGION,
                **{case.relationship: only_data.peers(only_data.peer(REGION_PEER_ID, REGION))},
            )
        ],
    )
    only_data.add_page(httpx_mock, REGION, [only_data.node_data(REGION_PEER_ID, REGION, name={"value": "World"})])
    add_counts(httpx_mock, {REGION: 1})
    client = only_data.client_of(only_clients, client_type)
    manager = getattr(region, case.relationship)

    await resolve(manager.fetch(only=["name"]))

    assert body_of(httpx_mock, "Get_LocationRegion") == only_data.expected_body(
        REGION,
        "Get_LocationRegion",
        {case.relationship: {"edges": {"node": {"...on LocationGeneric": only_data.REFERENCE}}}},
        filters={"ids": [only_data.REGION_ID]},
    )
    assert [manager.is_loaded, manager.peer_ids] == [True, [REGION_PEER_ID]]
    stored_peer = client.store.get(key=REGION_PEER_ID, kind=REGION)
    assert [stored_peer._get_attribute("name").value, stored_peer._only_marker] == ["World", OnlyMarker(only=("name",))]
    assert client.store.get(key=only_data.REGION_ID, kind=REGION) is region


@pytest.mark.parametrize("client_type", client_types)
async def test_peers_from_manager_fetch_with_only_carry_the_marker(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    [shelter] = await query_all(
        only_clients, client_type, httpx_mock, kind=SHELTER, edge=SHELTER_WITH_ANIMALS, only=["animals"]
    )
    only_data.add_page(httpx_mock, CAT, [only_data.node_data(only_data.CAT_ID, CAT, name={"value": "Tom"})])
    only_data.add_page(httpx_mock, DOG, [only_data.node_data(only_data.DOG_ID, DOG, name={"value": "Rex"})])
    add_counts(httpx_mock, {CAT: 1, DOG: 1})
    client = only_data.client_of(only_clients, client_type)

    await resolve(shelter.animals.fetch(only=["name"]))

    for kind, id in ((CAT, only_data.CAT_ID), (DOG, only_data.DOG_ID)):
        assert body_of(httpx_mock, f"Filters_{kind}") == only_data.expected_body(
            kind, f"Filters_{kind}", {"name": only_data.VALUE}, filters={"ids": [id], "order": PEER_ORDER}
        )
    cat = client.store.get(key=only_data.CAT_ID, kind=CAT)
    dog = client.store.get(key=only_data.DOG_ID, kind=DOG)
    assert [
        (cat._get_attribute("name").value, cat._only_marker),
        (dog._get_attribute("name").value, dog._only_marker),
    ] == [
        ("Tom", OnlyMarker(only=("name",))),
        ("Rex", OnlyMarker(only=("name",))),
    ]
    with pytest.raises(FieldNotLoadedError, match=not_fetched(CAT, "owner", ["name"])):
        _ = cat._get_relationship_one("owner").id


@pytest.mark.parametrize("client_type", client_types)
async def test_related_node_fetch_without_only_behaves_as_before(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    [device] = await query_all(only_clients, client_type, httpx_mock, kind=DEVICE, edge=DEVICE_WITH_SITE, only=None)
    only_data.add_page(
        httpx_mock,
        SITE,
        [only_data.node_data(only_data.SITE_ID, SITE, name={"value": "Paris"}, description={"value": "Main site"})],
    )
    client = only_data.client_of(only_clients, client_type)

    await resolve(device.site.fetch())

    assert body_of(httpx_mock, "Get_InfraSite") == default_body(
        SITE,
        "Get_InfraSite",
        {"name": only_data.VALUE, "description": only_data.VALUE},
        filters={"ids": [only_data.SITE_ID]},
    )
    site = device.site.peer
    assert [site.name.value, site.description.value, site._only_marker] == ["Paris", "Main site", None]
    assert [device.site.hfid, device.site.hfid_str] == [["Paris"], "InfraSite__Paris"]
    assert client.store.get(key=only_data.SITE_ID, kind=SITE) is site


@pytest.mark.parametrize("client_type", client_types)
async def test_manager_fetch_without_only_behaves_as_before(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    edge = only_data.node_data(only_data.DEVICE_ID, DEVICE, name={"value": "dev1"})
    [device] = await query_all(only_clients, client_type, httpx_mock, kind=DEVICE, edge=edge, only=None)
    only_data.add_page(
        httpx_mock,
        DEVICE,
        [only_data.node_data(only_data.DEVICE_ID, DEVICE, tags=only_data.peers(only_data.peer(only_data.TAG_ID, TAG)))],
    )
    only_data.add_page(httpx_mock, TAG, [only_data.node_data(only_data.TAG_ID, TAG, name={"value": "red"})])
    add_counts(httpx_mock, {TAG: 1})
    client = only_data.client_of(only_clients, client_type)

    await resolve(device.tags.fetch())

    assert body_of(httpx_mock, "Get_InfraDevice") == default_body(
        DEVICE,
        "Get_InfraDevice",
        {"tags": {"edges": {"node": {**NODE_FIELDS, "name": only_data.VALUE}}}},
        filters={"ids": [only_data.DEVICE_ID]},
    )
    assert body_of(httpx_mock, "Filters_BuiltinTag") == default_body(
        TAG, "Filters_BuiltinTag", {"name": only_data.VALUE}, filters={"ids": [only_data.TAG_ID], "order": PEER_ORDER}
    )
    assert [device.tags.is_loaded, device.tags.peer_ids] == [True, [only_data.TAG_ID]]
    stored_tag = client.store.get(key=only_data.TAG_ID, kind=TAG)
    assert [stored_tag._get_attribute("name").value, stored_tag._only_marker] == ["red", None]
