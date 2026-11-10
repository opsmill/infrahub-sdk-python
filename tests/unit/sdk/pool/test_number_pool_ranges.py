"""Tests that the ranges declared on a CoreNumberPool are sent as bounds, as its mutations take them."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.exceptions import FeatureNotSupportedError
from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync, RelatedNode, RelatedNodeSync
from infrahub_sdk.spec.object import ObjectFile

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI, RelationshipSchemaAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

REFUSAL_MESSAGE = re.escape(
    "The peers of 'ranges' cannot be edited one at a time, because the mutation takes the fields of a "
    "CoreNumberPoolRange and not a reference to one. To set them, pass the complete list of 'ranges' to "
    "client.create() and save the node with allow_upsert=True, or create, update or delete the "
    "CoreNumberPoolRange node itself."
)

POOL_ID = "nnnnnnnn-nnnn-nnnn-nnnn-nnnnnnnnnnnn"
POOL_DATA: dict[str, Any] = {"name": "VLAN IDs", "node": "InfraVLAN", "node_attribute": "vlan_id"}
# Wrapped as a query edge: the pool's own `node` attribute would otherwise be read as the edge's node.
FETCHED_POOL_DATA: dict[str, Any] = {
    "node": {
        "id": POOL_ID,
        "name": {"value": "VLAN IDs"},
        "node": {"value": "InfraVLAN"},
        "node_attribute": {"value": "vlan_id"},
        "ranges": {
            "edges": [
                {"node": {"id": "range-1", "display_label": "64512 - 65000", "__typename": "CoreNumberPoolRange"}},
            ]
        },
    }
}


def _make_node(
    clients: BothClients, client_type: str, schema: NodeSchemaAPI, data: dict[str, Any]
) -> InfrahubNode | InfrahubNodeSync:
    if client_type == "standard":
        return InfrahubNode(client=clients.standard, schema=schema, data=data)
    return InfrahubNodeSync(client=clients.sync, schema=schema, data=data)


def _make_peer(
    clients: BothClients, client_type: str, schema: RelationshipSchemaAPI, data: object
) -> RelatedNode | RelatedNodeSync:
    if client_type == "standard":
        return RelatedNode(client=clients.standard, branch="main", schema=schema, data=data)
    return RelatedNodeSync(client=clients.sync, branch="main", schema=schema, data=data)


async def _save(node: InfrahubNode | InfrahubNodeSync, allow_upsert: bool = False) -> None:
    if isinstance(node, InfrahubNode):
        await node.save(allow_upsert=allow_upsert)
    else:
        node.save(allow_upsert=allow_upsert)


@pytest.mark.parametrize("client_type", client_types)
async def test_create_sends_declared_ranges(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    ranges = [{"start": 64512, "end": 65000, "allocation_weight": 10}, {"start": 65001}]
    pool = _make_node(clients, client_type, number_pool_schema, {**POOL_DATA, "ranges": ranges})

    input_data = pool._generate_input_data()["data"]["data"]

    assert input_data["ranges"] == ranges


@pytest.mark.parametrize("client_type", client_types)
async def test_upsert_renders_declared_ranges(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, httpx_mock: HTTPXMock, client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"CoreNumberPoolUpsert": {"ok": True, "object": {"id": POOL_ID}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-corenumberpool-upsert"},
    )
    pool = _make_node(
        clients,
        client_type,
        number_pool_schema,
        {**POOL_DATA, "ranges": [{"start": 64512, "end": 65000, "allocation_weight": 10}, {"start": 65001}]},
    )

    await _save(pool, allow_upsert=True)

    request = httpx_mock.get_request(match_headers={"X-Infrahub-Tracker": "mutation-corenumberpool-upsert"})
    assert request is not None
    query = " ".join(json.loads(request.content)["query"].split())
    assert "ranges: [ { start: 64512 end: 65000 allocation_weight: 10 }, { start: 65001 }, ]" in query


@pytest.mark.parametrize("client_type", client_types)
async def test_empty_ranges_are_sent(clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str) -> None:
    pool = _make_node(clients, client_type, number_pool_schema, {**POOL_DATA, "ranges": []})

    input_data = pool._generate_input_data()["data"]["data"]

    assert input_data["ranges"] == []


@pytest.mark.parametrize("client_type", client_types)
async def test_ranges_left_out_are_not_sent(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    pool = _make_node(clients, client_type, number_pool_schema, POOL_DATA)

    input_data = pool._generate_input_data()["data"]["data"]

    assert "ranges" not in input_data


@dataclass
class RangeReferenceCase:
    name: str
    declared: Any


RANGE_REFERENCE_CASES = [
    RangeReferenceCase(name="id-string", declared="range-1"),
    RangeReferenceCase(name="id-dict", declared={"id": "range-1"}),
]


@pytest.mark.parametrize("client_type", client_types)
@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in RANGE_REFERENCE_CASES])
async def test_range_given_by_id_is_sent_as_reference(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str, case: RangeReferenceCase
) -> None:
    pool = _make_node(clients, client_type, number_pool_schema, {**POOL_DATA, "ranges": [case.declared]})

    input_data = pool._generate_input_data()["data"]["data"]

    assert input_data["ranges"] == [{"id": "range-1"}]


@pytest.mark.parametrize("client_type", client_types)
async def test_declared_ranges_are_not_resent_after_save(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, httpx_mock: HTTPXMock, client_type: str
) -> None:
    httpx_mock.add_response(
        method="POST",
        json={"data": {"CoreNumberPoolCreate": {"ok": True, "object": {"id": POOL_ID}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-corenumberpool-create"},
    )
    pool = _make_node(clients, client_type, number_pool_schema, {**POOL_DATA, "ranges": [{"start": 1, "end": 10}]})

    await _save(pool)

    assert "ranges" not in pool._generate_input_data(exclude_unmodified=True)["data"]["data"]


@pytest.mark.parametrize("client_type", client_types)
async def test_fetched_pool_keeps_range_peers_and_sends_no_ranges(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    pool = _make_node(clients, client_type, number_pool_schema, FETCHED_POOL_DATA)

    assert pool._get_relationship_many("ranges").peer_ids == ["range-1"]
    assert pool._generate_input_data(exclude_unmodified=True)["data"]["data"] == {"id": POOL_ID}


def _assert_the_pool_is_unchanged(pool: InfrahubNode | InfrahubNodeSync) -> None:
    assert pool._get_relationship_many("ranges").peer_ids == ["range-1"]
    assert pool._generate_input_data(exclude_unmodified=True)["data"]["data"] == {"id": POOL_ID}


@pytest.mark.parametrize("client_type", client_types)
async def test_adding_bounds_to_the_ranges_of_a_pool_is_refused(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    pool = _make_node(clients, client_type, number_pool_schema, FETCHED_POOL_DATA)

    with pytest.raises(FeatureNotSupportedError, match=REFUSAL_MESSAGE):
        pool._get_relationship_many("ranges").add({"start": 3000, "end": 3999})

    _assert_the_pool_is_unchanged(pool)


@pytest.mark.parametrize("client_type", client_types)
async def test_adding_a_range_by_reference_to_a_pool_is_refused(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    pool = _make_node(clients, client_type, number_pool_schema, FETCHED_POOL_DATA)

    with pytest.raises(FeatureNotSupportedError, match=REFUSAL_MESSAGE):
        pool._get_relationship_many("ranges").add("range-2")

    _assert_the_pool_is_unchanged(pool)


@pytest.mark.parametrize("client_type", client_types)
async def test_extending_the_ranges_of_a_pool_is_refused(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    pool = _make_node(clients, client_type, number_pool_schema, FETCHED_POOL_DATA)

    with pytest.raises(FeatureNotSupportedError, match=REFUSAL_MESSAGE):
        pool._get_relationship_many("ranges").extend([{"start": 3000}, {"start": 5000}])

    _assert_the_pool_is_unchanged(pool)


@pytest.mark.parametrize("client_type", client_types)
async def test_extending_the_ranges_of_a_pool_with_nothing_is_refused(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    """An empty iterable never reaches add(), so extend() has to refuse on its own."""
    pool = _make_node(clients, client_type, number_pool_schema, FETCHED_POOL_DATA)

    with pytest.raises(FeatureNotSupportedError, match=REFUSAL_MESSAGE):
        pool._get_relationship_many("ranges").extend([])

    _assert_the_pool_is_unchanged(pool)


@pytest.mark.parametrize("client_type", client_types)
async def test_removing_a_range_from_a_pool_is_refused(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    pool = _make_node(clients, client_type, number_pool_schema, FETCHED_POOL_DATA)

    with pytest.raises(FeatureNotSupportedError, match=REFUSAL_MESSAGE):
        pool._get_relationship_many("ranges").remove("range-1")

    _assert_the_pool_is_unchanged(pool)


async def test_changing_the_peer_list_of_a_pool_that_exists_sends_nothing(
    clients: BothClients, number_pool_schema: NodeSchemaAPI
) -> None:
    """A save of a pool Infrahub already holds sends the peers it was fetched with."""
    pool = InfrahubNode(client=clients.standard, schema=number_pool_schema, data=FETCHED_POOL_DATA)
    ranges = pool._get_relationship_many("ranges")

    ranges.peers.append(
        RelatedNode(client=clients.standard, branch="main", schema=ranges.schema, data={"start": 50, "end": 60})
    )

    assert pool._generate_input_data(exclude_unmodified=True)["data"]["data"] == {"id": POOL_ID}


async def test_changing_the_peer_list_before_the_pool_exists_sets_what_is_sent(
    clients: BothClients, number_pool_schema: NodeSchemaAPI
) -> None:
    """The create sends the list as it stands, so the peer list still decides the ranges."""
    pool = InfrahubNode(
        client=clients.standard, schema=number_pool_schema, data={**POOL_DATA, "ranges": [{"start": 1, "end": 10}]}
    )
    ranges = pool._get_relationship_many("ranges")

    ranges.peers.append(
        RelatedNode(client=clients.standard, branch="main", schema=ranges.schema, data={"start": 50, "end": 60})
    )

    assert pool._generate_input_data()["data"]["data"]["ranges"] == [
        {"start": 1, "end": 10},
        {"start": 50, "end": 60},
    ]


async def test_another_relationship_to_a_range_stays_editable(
    clients: BothClients, range_policy_schema: NodeSchemaAPI
) -> None:
    """Only the relationship Infrahub takes as bounds is refused, not every relationship to a range."""
    policy = InfrahubNode(
        client=clients.standard, schema=range_policy_schema, data={"name": "Even numbers", "allowed_ranges": []}
    )
    allowed = policy._get_relationship_many("allowed_ranges")

    allowed.add("range-1")
    allowed.peers.append(RelatedNode(client=clients.standard, branch="main", schema=allowed.schema, data="range-2"))

    assert allowed.peer_ids == ["range-1", "range-2"]
    assert policy._generate_input_data()["data"]["data"]["allowed_ranges"] == [{"id": "range-1"}, {"id": "range-2"}]


@dataclass
class ObjectFileRangeCase:
    name: str
    declared: Any


OBJECT_FILE_RANGE_CASES = [
    ObjectFileRangeCase(name="ranges-hold-one-data-list", declared={"data": [{"start": 3000, "end": 3099}]}),
    ObjectFileRangeCase(name="each-range-holds-its-data", declared=[{"data": {"start": 3000, "end": 3099}}]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in OBJECT_FILE_RANGE_CASES])
async def test_object_file_sends_the_declared_ranges_with_the_pool(
    clients: BothClients,
    number_pool_schema: NodeSchemaAPI,
    number_pool_range_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
    case: ObjectFileRangeCase,
) -> None:
    """A range an object file declares is a bound of the pool, not a node to create next to it."""
    client = clients.standard
    client.schema.set_cache(
        schema={"nodes": [number_pool_schema.model_dump(), number_pool_range_schema.model_dump()]}, branch="main"
    )
    httpx_mock.add_response(
        method="POST",
        json={"data": {"CoreNumberPoolUpsert": {"ok": True, "object": {"id": POOL_ID}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-corenumberpool-upsert"},
    )
    obj = ObjectFile(
        location=Path("inline"),
        content={
            "apiVersion": "infrahub.app/v1",
            "kind": "Object",
            "spec": {"kind": "CoreNumberPool", "data": [{**POOL_DATA, "ranges": case.declared}]},
        },
    )
    await obj.validate_format(client=client)

    # A request for anything other than the pool mutation, a range node of its own among them, has no
    # response registered and fails the test.
    await obj.process(client=client)

    request = httpx_mock.get_request(match_headers={"X-Infrahub-Tracker": "mutation-corenumberpool-upsert"})
    assert request is not None
    query = " ".join(json.loads(request.content)["query"].split())
    assert "ranges: [ { start: 3000 end: 3099 }, ]" in query


async def test_object_file_points_the_pool_at_a_range_it_names(
    clients: BothClients,
    number_pool_schema: NodeSchemaAPI,
    number_pool_range_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    """An object file that names existing ranges still points the pool at them."""
    client = clients.standard
    client.schema.set_cache(
        schema={"nodes": [number_pool_schema.model_dump(), number_pool_range_schema.model_dump()]}, branch="main"
    )
    httpx_mock.add_response(
        method="POST",
        json={"data": {"CoreNumberPoolUpsert": {"ok": True, "object": {"id": POOL_ID}}}},
        match_headers={"X-Infrahub-Tracker": "mutation-corenumberpool-upsert"},
    )
    obj = ObjectFile(
        location=Path("inline"),
        content={
            "apiVersion": "infrahub.app/v1",
            "kind": "Object",
            "spec": {"kind": "CoreNumberPool", "data": [{**POOL_DATA, "ranges": ["range-1"]}]},
        },
    )
    await obj.validate_format(client=client)

    await obj.process(client=client)

    request = httpx_mock.get_request(match_headers={"X-Infrahub-Tracker": "mutation-corenumberpool-upsert"})
    assert request is not None
    query = " ".join(json.loads(request.content)["query"].split())
    assert 'ranges: [ { id: "range-1" }, ]' in query
