"""Tests for InfrahubClient.get_many and its query compiler.

Pure-function tests cover the compiler's output and error paths;
parametrized BothClients tests cover the full HTTP round trip via
``httpx_mock`` at the transport boundary.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from infrahub_sdk.client import compile_get_many_query
from infrahub_sdk.exceptions import NodeNotFoundError, ValidationError

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from infrahub_sdk.schema import NodeSchemaAPI

    from .conftest import BothClients


GET_MANY_URL = "http://mock/graphql/main"


# --- compiler (pure logic) --------------------------------------------------


def test_single_kind_single_id_single_attribute() -> None:
    query, variables, kinds = compile_get_many_query({"InfraDevice": {"ids": ["dev-1"], "attributes": ["name"]}})
    assert kinds == ["InfraDevice"]
    assert variables == {"ids_0": ["dev-1"]}
    assert query == (
        "query GetMany($ids_0: [ID]) { "
        "k0: InfraDevice(ids: $ids_0) "
        "{ edges { node { __typename id name { value } } } } }"
    )


def test_multiple_kinds_emit_one_alias_per_block() -> None:
    query, variables, kinds = compile_get_many_query(
        {
            "InfraAutonomousSystem": {"ids": ["as-1", "as-2"], "attributes": ["asn"]},
            "InfraDevice": {"ids": ["dev-1"], "attributes": ["role", "name"]},
        }
    )
    assert kinds == ["InfraAutonomousSystem", "InfraDevice"]
    assert variables == {"ids_0": ["as-1", "as-2"], "ids_1": ["dev-1"]}
    assert "k0: InfraAutonomousSystem(ids: $ids_0)" in query
    assert "k1: InfraDevice(ids: $ids_1)" in query
    assert "asn { value }" in query
    # Attribute selection is sorted within a block.
    assert query.index("name { value }") < query.index("role { value }")
    assert "$ids_0: [ID]" in query
    assert "$ids_1: [ID]" in query


def test_duplicate_ids_are_deduplicated_and_sorted() -> None:
    _query, variables, _kinds = compile_get_many_query(
        {"InfraDevice": {"ids": ["dev-2", "dev-1", "dev-1", "dev-2"], "attributes": ["name"]}}
    )
    assert variables == {"ids_0": ["dev-1", "dev-2"]}


def test_duplicate_attributes_are_deduplicated() -> None:
    query, _variables, _kinds = compile_get_many_query(
        {"InfraDevice": {"ids": ["dev-1"], "attributes": ["name", "name", "role"]}}
    )
    assert query.count("name { value }") == 1
    assert query.count("role { value }") == 1


def test_omitted_attributes_emits_minimal_selection() -> None:
    query, _variables, _kinds = compile_get_many_query({"InfraDevice": {"ids": ["dev-1"]}})
    assert "node { __typename id }" in query
    assert "{ value }" not in query


def test_empty_attributes_list_emits_minimal_selection() -> None:
    query, _variables, _kinds = compile_get_many_query({"InfraDevice": {"ids": ["dev-1"], "attributes": []}})
    assert "node { __typename id }" in query


def test_kind_order_in_spec_is_preserved() -> None:
    _query, _variables, kinds = compile_get_many_query(
        {"Zeta": {"ids": ["z"]}, "Alpha": {"ids": ["a"]}, "Mu": {"ids": ["m"]}}
    )
    assert kinds == ["Zeta", "Alpha", "Mu"]


def test_empty_spec_raises() -> None:
    with pytest.raises(ValidationError, match="spec must contain at least one kind"):
        compile_get_many_query({})


def test_empty_ids_list_raises() -> None:
    with pytest.raises(ValidationError, match="'ids' must be a non-empty list"):
        compile_get_many_query({"InfraDevice": {"ids": [], "attributes": ["name"]}})


def test_missing_ids_key_raises() -> None:
    with pytest.raises(ValidationError, match="'ids' must be a non-empty list"):
        compile_get_many_query({"InfraDevice": {"attributes": ["name"]}})


def test_non_mapping_entry_raises() -> None:
    with pytest.raises(ValidationError, match="entry must be a mapping"):
        compile_get_many_query({"InfraDevice": ["dev-1"]})  # type: ignore[dict-item]


def test_invalid_kind_identifier_raises() -> None:
    with pytest.raises(ValidationError, match="not a valid GraphQL identifier"):
        compile_get_many_query({"Infra Device": {"ids": ["dev-1"]}})


def test_invalid_attribute_name_raises() -> None:
    with pytest.raises(ValidationError, match="invalid attribute names"):
        compile_get_many_query({"InfraDevice": {"ids": ["dev-1"], "attributes": ["name", "bad name"]}})


def test_string_ids_rejected_not_iterated_as_chars() -> None:
    # Passing a bare string would silently iterate character-by-character and
    # send N one-character GraphQL ids. Reject up front.
    with pytest.raises(ValidationError, match="'ids' must be a non-empty list"):
        compile_get_many_query({"InfraDevice": {"ids": "dev-1"}})  # type: ignore[dict-item]


def test_bytes_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="'ids' must be a non-empty list"):
        compile_get_many_query({"InfraDevice": {"ids": b"dev-1"}})  # type: ignore[dict-item]


def test_string_attributes_rejected_not_iterated_as_chars() -> None:
    # Same trap as ``ids``: a bare string would split into single-character
    # field names that each pass the GraphQL identifier regex.
    with pytest.raises(ValidationError, match="'attributes' must be a list"):
        compile_get_many_query({"InfraDevice": {"ids": ["dev-1"], "attributes": "name"}})  # type: ignore[dict-item]


def test_bytes_attributes_rejected() -> None:
    with pytest.raises(ValidationError, match="'attributes' must be a list"):
        compile_get_many_query({"InfraDevice": {"ids": ["dev-1"], "attributes": b"name"}})  # type: ignore[dict-item]


def test_multiple_problems_are_collected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        compile_get_many_query(
            {
                "InfraDevice": {"ids": []},
                "Bad Kind": {"ids": ["a"]},
                "InfraSite": {"ids": ["s"], "attributes": ["bad attr"]},
            }
        )
    assert excinfo.value.messages is not None
    assert len(excinfo.value.messages) == 3


# --- client methods (httpx_mock at the transport boundary) ------------------


def _seed_schema(clients: BothClients, schema: NodeSchemaAPI) -> None:
    cache_data = {"version": "1.0", "nodes": [schema.model_dump()]}
    clients.standard.schema.set_cache(cache_data)
    clients.sync.schema.set_cache(cache_data)


def _location_response(*, ids: list[str]) -> dict:
    return {
        "data": {
            "k0": {
                "edges": [
                    {
                        "node": {
                            "__typename": "BuiltinLocation",
                            "id": node_id,
                            "name": {"value": f"site-{node_id}"},
                            "type": {"value": "datacenter"},
                        }
                    }
                    for node_id in ids
                ]
            }
        }
    }


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_get_many_single_kind_round_trip(
    clients: BothClients,
    client_type: str,
    location_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    _seed_schema(clients, location_schema)
    httpx_mock.add_response(
        method="POST",
        url=GET_MANY_URL,
        match_headers={"X-Infrahub-Tracker": "query-get-many"},
        json=_location_response(ids=["loc-1", "loc-2"]),
    )
    spec = {"BuiltinLocation": {"ids": ["loc-2", "loc-1"], "attributes": ["name", "type"]}}

    if client_type == "standard":
        result = await clients.standard.get_many(spec)
    else:
        result = clients.sync.get_many(spec)

    assert list(result.keys()) == ["BuiltinLocation"]
    nodes = result["BuiltinLocation"]
    assert len(nodes) == 2
    assert {node.id for node in nodes} == {"loc-1", "loc-2"}
    assert {node.get_kind() for node in nodes} == {"BuiltinLocation"}

    # The compiled query uses sorted/deduplicated ids
    sent = json.loads(httpx_mock.get_requests()[0].content)
    assert sent["variables"] == {"ids_0": ["loc-1", "loc-2"]}
    assert "k0: BuiltinLocation(ids: $ids_0)" in sent["query"]


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_get_many_populates_store_when_enabled(
    clients: BothClients,
    client_type: str,
    location_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    _seed_schema(clients, location_schema)
    httpx_mock.add_response(
        method="POST",
        url=GET_MANY_URL,
        match_headers={"X-Infrahub-Tracker": "query-get-many"},
        json=_location_response(ids=["loc-1"]),
    )
    spec = {"BuiltinLocation": {"ids": ["loc-1"], "attributes": ["name"]}}

    if client_type == "standard":
        await clients.standard.get_many(spec)
        stored = clients.standard.store.get(key="loc-1")
    else:
        clients.sync.get_many(spec)
        stored = clients.sync.store.get(key="loc-1")

    assert stored.id == "loc-1"


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_get_many_skips_store_when_disabled(
    clients: BothClients,
    client_type: str,
    location_schema: NodeSchemaAPI,
    httpx_mock: HTTPXMock,
) -> None:
    _seed_schema(clients, location_schema)
    httpx_mock.add_response(
        method="POST",
        url=GET_MANY_URL,
        match_headers={"X-Infrahub-Tracker": "query-get-many"},
        json=_location_response(ids=["loc-1"]),
    )
    spec = {"BuiltinLocation": {"ids": ["loc-1"], "attributes": ["name"]}}

    if client_type == "standard":
        await clients.standard.get_many(spec, populate_store=False)
        store = clients.standard.store
    else:
        clients.sync.get_many(spec, populate_store=False)
        store = clients.sync.store

    with pytest.raises(NodeNotFoundError):
        store.get(key="loc-1")


@pytest.mark.parametrize("client_type", ["standard", "sync"])
async def test_get_many_raises_on_invalid_spec_without_calling_server(
    clients: BothClients,
    client_type: str,
    httpx_mock: HTTPXMock,
) -> None:
    spec = {"BuiltinLocation": {"ids": []}}

    if client_type == "standard":
        with pytest.raises(ValidationError, match="'ids' must be a non-empty list"):
            await clients.standard.get_many(spec)
    else:
        with pytest.raises(ValidationError, match="'ids' must be a non-empty list"):
            clients.sync.get_many(spec)

    # The compile failure short-circuits before any HTTP call is made.
    assert httpx_mock.get_requests() == []
