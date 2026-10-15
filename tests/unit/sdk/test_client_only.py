from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import (
    FieldNotFoundError,
    FieldNotLoadedError,
    FieldSelectionConflictError,
    NodeNotFoundError,
)
from infrahub_sdk.node._only import OnlyMarker  # noqa: PLC2701  # the helpers under test are private to the package
from tests.helpers.only_data import (
    CAT_ID,
    DEVICE_ID,
    DEVICE_WITH_HFID,
    DOG_ID,
    PARENT_ID,
    REFERENCE,
    REGION_ID,
    SITE_ID,
    TAG_2_ID,
    TAG_ID,
    VALUE,
    add_page,
    client_of,
    expected_body,
    node_data,
    peer,
    peers,
    query_nodes,
    run,
)

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tests.unit.sdk.conftest import BothClients

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)

client_types = ["standard", "sync"]

DEVICE_2_ID = "a5f1d5a0-5f5c-4a2b-9a4c-3e1c4c1f0d02"
OWNER_ID = "e9b5f9e4-9d9a-4e6f-9e8a-7c5a8a5b4b01"
OWNER_2_ID = "e9b5f9e4-9d9a-4e6f-9e8a-7c5a8a5b4b02"
WALKER_ID = "e9b5f9e4-9d9a-4e6f-9e8a-7c5a8a5b4b03"
HOME_ID = "b6e2c6b1-6a6d-4b3c-8b5d-4f2d5d2e1e02"
CHILD_ID = "f1a6e1f5-1e1b-4f7a-8f9b-8d6b9b6c5c03"
ANCESTOR_ID = "f1a6e1f5-1e1b-4f7a-8f9b-8d6b9b6c5c04"
DESCENDANT_ID = "f1a6e1f5-1e1b-4f7a-8f9b-8d6b9b6c5c05"


@dataclass
class ConflictCase:
    name: str
    method: str
    arguments: dict[str, Any]


CONFLICT_CASES = [
    ConflictCase(name="get-with-include", method="get", arguments={"id": DEVICE_ID, "include": ["tags"]}),
    ConflictCase(name="get-with-empty-exclude", method="get", arguments={"id": DEVICE_ID, "exclude": []}),
    ConflictCase(name="all-with-exclude", method="all", arguments={"exclude": ["description"]}),
    ConflictCase(name="all-with-empty-include", method="all", arguments={"include": []}),
    ConflictCase(name="filters-with-include", method="filters", arguments={"include": ["tags"], "name__value": "x"}),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in CONFLICT_CASES])
async def test_only_with_include_or_exclude_raises_before_any_request(
    clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: ConflictCase
) -> None:
    with pytest.raises(FieldSelectionConflictError, match="only cannot be combined with include or exclude"):
        await run(clients, client_type, case.method, kind="InfraDevice", only=["name"], **case.arguments)

    assert httpx_mock.get_requests() == []


@dataclass
class UnknownNameCase:
    name: str
    method: str
    kind: str
    only: list[str]
    message: str
    arguments: dict[str, Any] = field(default_factory=dict)


UNKNOWN_NAME_CASES = [
    UnknownNameCase(
        name="get-misspelt-name",
        method="get",
        kind="InfraDevice",
        only=["nmae"],
        message="'nmae' is not an attribute or relationship of InfraDevice",
        arguments={"id": DEVICE_ID},
    ),
    UnknownNameCase(
        name="all-misspelt-name",
        method="all",
        kind="InfraDevice",
        only=["name", "stie"],
        message="'stie' is not an attribute or relationship of InfraDevice",
    ),
    UnknownNameCase(
        name="filters-misspelt-name",
        method="filters",
        kind="InfraDevice",
        only=["descripton"],
        message="'descripton' is not an attribute or relationship of InfraDevice",
        arguments={"name__value": "dev1"},
    ),
    UnknownNameCase(
        name="ancestors-on-kind-without-hierarchy",
        method="all",
        kind="InfraSite",
        only=["ancestors"],
        message="'ancestors' is not an attribute or relationship of InfraSite",
    ),
    UnknownNameCase(
        name="name-on-no-implementing-kind",
        method="all",
        kind="TestingAnimal",
        only=["leash"],
        message="'leash' is not an attribute or relationship of TestingAnimal",
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in UNKNOWN_NAME_CASES])
async def test_unknown_name_in_only_raises_before_the_query(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: UnknownNameCase
) -> None:
    with pytest.raises(FieldNotFoundError, match=case.message):
        await run(only_clients, client_type, case.method, kind=case.kind, only=case.only, **case.arguments)

    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("client_type", client_types)
async def test_only_given_as_a_string_raises_before_the_query(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    with pytest.raises(TypeError, match="only must be a list of field names, not a string"):
        await run(only_clients, client_type, "all", kind="InfraDevice", only="name")

    assert httpx_mock.get_requests() == []


@dataclass
class IgnoredNameCase:
    name: str
    arguments: dict[str, Any]


IGNORED_NAME_CASES = [
    IgnoredNameCase(name="include", arguments={"include": ["nmae"]}),
    IgnoredNameCase(name="exclude", arguments={"exclude": ["nmae"]}),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in IGNORED_NAME_CASES])
async def test_unknown_name_in_include_or_exclude_is_ignored(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: IgnoredNameCase
) -> None:
    add_page(httpx_mock, "InfraDevice", [])

    await run(only_clients, client_type, "all", kind="InfraDevice")
    await run(only_clients, client_type, "all", kind="InfraDevice", **case.arguments)

    default_body, body = [json.loads(request.content) for request in httpx_mock.get_requests()]
    assert body["operationName"] == "All_InfraDevice"
    assert body == default_body


@dataclass
class RequestCase:
    name: str
    method: str
    kind: str
    only: list[str]
    expected: dict[str, Any]
    arguments: dict[str, Any] = field(default_factory=dict)


REQUEST_CASES = [
    RequestCase(
        name="all-attribute-and-relationship",
        method="all",
        kind="InfraDevice",
        only=["name", "site"],
        expected=expected_body("InfraDevice", "All_InfraDevice", {"name": VALUE, "site": {"node": REFERENCE}}),
    ),
    RequestCase(
        name="get-by-id",
        method="get",
        kind="InfraDevice",
        only=["description"],
        arguments={"id": DEVICE_ID},
        expected=expected_body("InfraDevice", "Get_InfraDevice", {"description": VALUE}, filters={"ids": [DEVICE_ID]}),
    ),
    RequestCase(
        name="filters-with-filter",
        method="filters",
        kind="InfraDevice",
        only=["tags"],
        arguments={"name__value": "dev1"},
        expected=expected_body(
            "InfraDevice",
            "Filters_InfraDevice",
            {"tags": {"edges": {"node": REFERENCE}}},
            filters={"name__value": "dev1"},
        ),
    ),
    RequestCase(
        name="name-only-on-implementing-kind",
        method="all",
        kind="TestingAnimal",
        only=["walker"],
        expected=expected_body(
            "TestingAnimal",
            "All_TestingAnimal",
            {"...on TestingDog": {"walker": {"node": REFERENCE, "@alias": "__alias__TestingDog__walker"}}},
        ),
    ),
    RequestCase(
        name="fragment-adds-nothing-on-generic",
        method="all",
        kind="TestingAnimal",
        only=["name", "walker"],
        arguments={"fragment": True},
        expected=expected_body(
            "TestingAnimal",
            "All_TestingAnimal",
            {
                "name": VALUE,
                "...on TestingDog": {"walker": {"node": REFERENCE, "@alias": "__alias__TestingDog__walker"}},
            },
        ),
    ),
    RequestCase(
        name="ancestors-on-hierarchical-kind",
        method="all",
        kind="LocationRegion",
        only=["ancestors"],
        expected=expected_body(
            "LocationRegion",
            "All_LocationRegion",
            {"ancestors": {"edges": {"node": {"...on LocationGeneric": REFERENCE}}}},
        ),
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in REQUEST_CASES])
async def test_only_request_body(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: RequestCase
) -> None:
    edges = [node_data(DEVICE_ID, case.kind)] if case.method == "get" else []
    add_page(httpx_mock, case.kind, edges)

    await run(only_clients, client_type, case.method, kind=case.kind, only=case.only, **case.arguments)

    request = httpx_mock.get_request()
    assert request is not None
    assert json.loads(request.content) == case.expected


@dataclass
class StoreCase:
    name: str
    kind: str
    only: list[str]
    edges: list[dict[str, Any]]
    expected_markers: dict[str, OnlyMarker]
    prefetch_relationships: bool = False


DEVICE_WITH_PEERS = node_data(
    DEVICE_ID,
    "InfraDevice",
    site=peer(SITE_ID, "InfraSite", name={"value": "Paris"}),
    tags=peers(peer(TAG_ID, "BuiltinTag", name={"value": "red"}), peer(TAG_2_ID, "BuiltinTag", name={"value": "blue"})),
)

STORE_CASES = [
    StoreCase(
        name="nodes-carry-the-marker",
        kind="InfraDevice",
        only=["name"],
        edges=[
            node_data(DEVICE_ID, "InfraDevice", name={"value": "dev1"}),
            node_data(DEVICE_2_ID, "InfraDevice", name={"value": "dev2"}),
        ],
        expected_markers={DEVICE_ID: OnlyMarker(only=("name",)), DEVICE_2_ID: OnlyMarker(only=("name",))},
    ),
    StoreCase(
        name="references-build-no-peers",
        kind="InfraDevice",
        only=["site", "tags"],
        edges=[DEVICE_WITH_PEERS],
        expected_markers={DEVICE_ID: OnlyMarker(only=("site", "tags"))},
    ),
    StoreCase(
        name="prefetch-builds-named-peers",
        kind="InfraDevice",
        only=["site", "tags"],
        prefetch_relationships=True,
        edges=[DEVICE_WITH_PEERS],
        expected_markers={
            DEVICE_ID: OnlyMarker(only=("site", "tags")),
            SITE_ID: OnlyMarker(only=("site", "tags"), peer_of="InfraDevice.site"),
            TAG_ID: OnlyMarker(only=("site", "tags"), peer_of="InfraDevice.tags"),
            TAG_2_ID: OnlyMarker(only=("site", "tags"), peer_of="InfraDevice.tags"),
        },
    ),
    StoreCase(
        name="prefetch-ignores-unnamed-relationship-in-response",
        kind="InfraDevice",
        only=["tags"],
        prefetch_relationships=True,
        edges=[DEVICE_WITH_PEERS],
        expected_markers={
            DEVICE_ID: OnlyMarker(only=("tags",)),
            TAG_ID: OnlyMarker(only=("tags",), peer_of="InfraDevice.tags"),
            TAG_2_ID: OnlyMarker(only=("tags",), peer_of="InfraDevice.tags"),
        },
    ),
    StoreCase(
        name="prefetch-and-hfid-build-named-and-hfid-peers",
        kind="InfraDevice",
        only=["tags", "hfid"],
        prefetch_relationships=True,
        edges=[DEVICE_WITH_PEERS],
        expected_markers={
            DEVICE_ID: OnlyMarker(only=("tags", "hfid")),
            SITE_ID: OnlyMarker(only=("tags", "hfid"), peer_of="InfraDevice.site"),
            TAG_ID: OnlyMarker(only=("tags", "hfid"), peer_of="InfraDevice.tags"),
            TAG_2_ID: OnlyMarker(only=("tags", "hfid"), peer_of="InfraDevice.tags"),
        },
    ),
    StoreCase(
        name="prefetch-builds-parent-and-children-only",
        kind="LocationRegion",
        only=["parent", "children", "ancestors", "descendants"],
        prefetch_relationships=True,
        edges=[
            node_data(
                REGION_ID,
                "LocationRegion",
                parent=peer(PARENT_ID, "LocationRegion", name={"value": "Europe"}),
                children=peers(peer(CHILD_ID, "LocationRegion", name={"value": "Paris"})),
                ancestors=peers(peer(ANCESTOR_ID, "LocationRegion", name={"value": "World"})),
                descendants=peers(peer(DESCENDANT_ID, "LocationRegion", name={"value": "Montmartre"})),
            )
        ],
        expected_markers={
            REGION_ID: OnlyMarker(only=("parent", "children", "ancestors", "descendants")),
            PARENT_ID: OnlyMarker(
                only=("parent", "children", "ancestors", "descendants"), peer_of="LocationRegion.parent"
            ),
            CHILD_ID: OnlyMarker(
                only=("parent", "children", "ancestors", "descendants"), peer_of="LocationRegion.children"
            ),
        },
    ),
    StoreCase(
        name="prefetch-builds-peer-of-relationship-only-on-implementing-kind",
        kind="TestingAnimal",
        only=["walker"],
        prefetch_relationships=True,
        edges=[
            node_data(
                DOG_ID,
                "TestingDog",
                __alias__TestingDog__walker=peer(WALKER_ID, "TestingPerson", name={"value": "Bob"}),
            ),
            node_data(CAT_ID, "TestingCat"),
        ],
        expected_markers={
            DOG_ID: OnlyMarker(only=("walker",)),
            CAT_ID: OnlyMarker(only=("walker",)),
            WALKER_ID: OnlyMarker(only=("walker",), peer_of="TestingDog.walker"),
        },
    ),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in STORE_CASES])
async def test_only_nodes_and_peers_in_store(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: StoreCase
) -> None:
    add_page(httpx_mock, case.kind, case.edges)
    client = client_of(only_clients, client_type)

    nodes = await query_nodes(
        only_clients,
        client_type,
        "all",
        kind=case.kind,
        only=case.only,
        prefetch_relationships=case.prefetch_relationships,
    )

    assert [node._only_marker for node in nodes] == [case.expected_markers[node.id] for node in nodes]
    assert client.store.count() == len(case.expected_markers)
    stored_markers = {id: client.store.get(key=id)._only_marker for id in case.expected_markers}
    assert stored_markers == case.expected_markers


@pytest.mark.parametrize("client_type", client_types)
async def test_peer_of_reference_is_not_found_when_not_in_store(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    add_page(httpx_mock, "InfraDevice", [DEVICE_WITH_PEERS])

    nodes = await query_nodes(only_clients, client_type, "all", kind="InfraDevice", only=["site"])

    assert nodes[0].site.id == SITE_ID
    with pytest.raises(NodeNotFoundError, match=f"Unable to find the node '{SITE_ID}' in the store"):
        _ = nodes[0].site.peer


@dataclass
class HfidCase:
    name: str
    populate_store: bool
    expected_store_count: int


HFID_CASES = [
    HfidCase(name="populate-store", populate_store=True, expected_store_count=2),
    HfidCase(name="no-store", populate_store=False, expected_store_count=0),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in HFID_CASES])
async def test_hfid_from_only_is_calculated(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str, case: HfidCase
) -> None:
    add_page(httpx_mock, "InfraDevice", [DEVICE_WITH_HFID])
    client = client_of(only_clients, client_type)

    nodes = await query_nodes(
        only_clients, client_type, "all", kind="InfraDevice", only=["hfid"], populate_store=case.populate_store
    )

    assert nodes[0].hfid == ["dev1", "Paris"]
    assert client.store.count() == case.expected_store_count


@pytest.mark.parametrize("client_type", client_types)
async def test_store_finds_node_from_only_by_hfid(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    add_page(httpx_mock, "InfraDevice", [DEVICE_WITH_HFID])
    client = client_of(only_clients, client_type)

    nodes = await query_nodes(only_clients, client_type, "all", kind="InfraDevice", only=["hfid"])

    assert client.store.get(key=["dev1", "Paris"], kind="InfraDevice") is nodes[0]
    assert client.store.get(key=SITE_ID, kind="InfraSite")._only_marker == OnlyMarker(
        only=("hfid",), peer_of="InfraDevice.site"
    )


@pytest.mark.parametrize("client_type", client_types)
async def test_hfid_does_not_change_when_store_gets_narrower_peer(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    add_page(httpx_mock, "InfraDevice", [DEVICE_WITH_HFID])
    add_page(httpx_mock, "InfraSite", [node_data(SITE_ID, "InfraSite", description={"value": "Main site"})])
    client = client_of(only_clients, client_type)

    devices = await query_nodes(only_clients, client_type, "all", kind="InfraDevice", only=["hfid"])
    sites = await query_nodes(only_clients, client_type, "all", kind="InfraSite", only=["description"])

    assert client.store.get(key=SITE_ID, kind="InfraSite") is sites[0]
    assert sites[0].hfid is None
    assert devices[0].hfid == ["dev1", "Paris"]


@pytest.mark.parametrize("client_type", client_types)
async def test_hfid_is_none_when_its_fields_were_not_fetched(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    add_page(httpx_mock, "InfraDevice", [node_data(DEVICE_ID, "InfraDevice", description={"value": "core"})])

    nodes = await query_nodes(only_clients, client_type, "all", kind="InfraDevice", only=["description"])

    assert nodes[0].hfid is None


@pytest.mark.parametrize("client_type", client_types)
async def test_hfid_of_each_implementing_kind_from_only(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    add_page(
        httpx_mock,
        "TestingAnimal",
        [
            node_data(
                CAT_ID,
                "TestingCat",
                name={"value": "Tom"},
                owner=peer(OWNER_ID, "TestingPerson", name={"value": "Alice"}),
                __alias__TestingCat__home=peer(HOME_ID, "InfraSite", name={"value": "Paris"}),
            ),
            node_data(
                DOG_ID,
                "TestingDog",
                name={"value": "Rex"},
                owner=peer(OWNER_2_ID, "TestingPerson", name={"value": "Carol"}),
            ),
        ],
    )
    client = client_of(only_clients, client_type)

    nodes = await query_nodes(only_clients, client_type, "all", kind="TestingAnimal", only=["hfid"])

    assert {node.id: node.hfid for node in nodes} == {CAT_ID: ["Paris", "Tom"], DOG_ID: ["Carol", "Rex"]}
    assert client.store.get(key=HOME_ID, kind="InfraSite")._only_marker == OnlyMarker(
        only=("hfid",), peer_of="TestingCat.home"
    )


@pytest.mark.parametrize("client_type", client_types)
async def test_node_from_only_replaces_fuller_copy_in_store(
    only_clients: BothClients, httpx_mock: HTTPXMock, client_type: str
) -> None:
    add_page(
        httpx_mock,
        "InfraDevice",
        [
            node_data(
                DEVICE_ID,
                "InfraDevice",
                name={"value": "dev1"},
                description={"value": "core"},
                site=peer(SITE_ID, "InfraSite"),
            )
        ],
    )
    add_page(httpx_mock, "InfraDevice", [node_data(DEVICE_ID, "InfraDevice", name={"value": "dev1"})])
    client = client_of(only_clients, client_type)

    fuller = await query_nodes(only_clients, client_type, "get", kind="InfraDevice", id=DEVICE_ID)
    narrower = await query_nodes(only_clients, client_type, "get", kind="InfraDevice", id=DEVICE_ID, only=["name"])

    assert fuller[0]._only_marker is None
    stored = client.store.get(key=DEVICE_ID, kind="InfraDevice")
    assert stored is narrower[0]
    assert stored._only_marker == OnlyMarker(only=("name",))
    message = "InfraDevice.description was not fetched: the node was queried with only=['name']."
    with pytest.raises(FieldNotLoadedError, match=re.escape(message)):
        _ = stored.description.value
