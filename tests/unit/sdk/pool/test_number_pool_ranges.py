"""Tests that the ranges declared on a CoreNumberPool are sent as bounds, as its mutations take them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from infrahub_sdk.node import InfrahubNode, InfrahubNodeSync

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI
    from tests.unit.sdk.conftest import BothClients

client_types = ["standard", "sync"]

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


def _make_pool(
    clients: BothClients, client_type: str, schema: NodeSchemaAPI, data: dict[str, Any]
) -> InfrahubNode | InfrahubNodeSync:
    if client_type == "standard":
        return InfrahubNode(client=clients.standard, schema=schema, data=data)
    return InfrahubNodeSync(client=clients.sync, schema=schema, data=data)


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
    pool = _make_pool(clients, client_type, number_pool_schema, {**POOL_DATA, "ranges": ranges})

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
    pool = _make_pool(
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
    pool = _make_pool(clients, client_type, number_pool_schema, {**POOL_DATA, "ranges": []})

    input_data = pool._generate_input_data()["data"]["data"]

    assert input_data["ranges"] == []


@pytest.mark.parametrize("client_type", client_types)
async def test_ranges_left_out_are_not_sent(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    pool = _make_pool(clients, client_type, number_pool_schema, POOL_DATA)

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
    pool = _make_pool(clients, client_type, number_pool_schema, {**POOL_DATA, "ranges": [case.declared]})

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
    pool = _make_pool(clients, client_type, number_pool_schema, {**POOL_DATA, "ranges": [{"start": 1, "end": 10}]})

    await _save(pool)

    assert "ranges" not in pool._generate_input_data(exclude_unmodified=True)["data"]["data"]


@pytest.mark.parametrize("client_type", client_types)
async def test_fetched_pool_keeps_range_peers_and_sends_no_ranges(
    clients: BothClients, number_pool_schema: NodeSchemaAPI, client_type: str
) -> None:
    pool = _make_pool(clients, client_type, number_pool_schema, FETCHED_POOL_DATA)

    assert pool._get_relationship_many("ranges").peer_ids == ["range-1"]
    assert pool._generate_input_data(exclude_unmodified=True)["data"]["data"] == {"id": POOL_ID}
