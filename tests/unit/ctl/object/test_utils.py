"""Unit tests for ``infrahub_sdk.ctl.object.utils``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrahub_sdk.ctl.object.utils import (
    prepare_relationship_data,
    raise_if_set_edits_inline_peers,
    raise_if_set_names_inline_peers_by_reference,
    resolve_node,
)
from infrahub_sdk.exceptions import FeatureNotSupportedError, NodeNotFoundError
from infrahub_sdk.schema import NodeSchema, NodeSchemaAPI


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a mock InfrahubClient with async schema and get methods."""
    client = MagicMock()
    client.schema = MagicMock()
    client.schema.get = AsyncMock()
    client.get = AsyncMock()
    return client


async def test_resolve_by_uuid(mock_client: MagicMock) -> None:
    """When the identifier is a valid UUID, ``client.get(id=...)`` is called directly."""
    mock_schema = MagicMock()
    mock_schema.default_filter = None
    mock_schema.human_friendly_id = None
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    uuid_identifier = "12345678-1234-5678-1234-567812345678"

    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=True):
        result = await resolve_node(mock_client, "InfraDevice", uuid_identifier)

    assert result is expected_node
    mock_client.get.assert_awaited_once_with(kind="InfraDevice", id=uuid_identifier, branch=None)


async def test_resolve_by_default_filter(mock_client: MagicMock) -> None:
    """When the schema has a ``default_filter``, it is used as a keyword filter."""
    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = "name__value"
    mock_schema.human_friendly_id = None
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False):
        result = await resolve_node(mock_client, "InfraDevice", "router1")

    assert result is expected_node
    mock_client.get.assert_awaited_once_with(
        kind="InfraDevice",
        branch=None,
        raise_when_missing=False,
        name__value="router1",
    )


async def test_resolve_by_hfid(mock_client: MagicMock) -> None:
    """When the schema defines ``human_friendly_id``, ``client.get(hfid=...)`` is used."""
    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = None
    mock_schema.human_friendly_id = ["name__value"]
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False):
        result = await resolve_node(mock_client, "InfraDevice", "router1")

    assert result is expected_node
    mock_client.get.assert_awaited_once_with(
        kind="InfraDevice",
        hfid=["router1"],
        branch=None,
        raise_when_missing=False,
    )


async def test_resolve_by_hfid_multi_component(mock_client: MagicMock) -> None:
    """Multi-component HFID strings (``a/b``) are split on ``/``."""
    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = None
    mock_schema.human_friendly_id = ["site__name__value", "name__value"]
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False):
        result = await resolve_node(mock_client, "InfraDevice", "london/router1")

    assert result is expected_node
    mock_client.get.assert_awaited_once_with(
        kind="InfraDevice",
        hfid=["london", "router1"],
        branch=None,
        raise_when_missing=False,
    )


async def test_resolve_fallback_raises(mock_client: MagicMock) -> None:
    """When no lookup strategy matches, NodeNotFoundError is raised directly."""
    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = None
    mock_schema.human_friendly_id = None
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    with (
        patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False),
        pytest.raises(NodeNotFoundError),
    ):
        await resolve_node(mock_client, "InfraDevice", "unknown-name")

    mock_client.get.assert_not_awaited()


async def test_resolve_uses_provided_schema(mock_client: MagicMock) -> None:
    """When ``schema`` is provided, ``client.schema.get`` is not called."""
    pre_fetched_schema = MagicMock(spec=NodeSchemaAPI)
    pre_fetched_schema.default_filter = None
    pre_fetched_schema.human_friendly_id = None

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    uuid_identifier = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=True):
        result = await resolve_node(mock_client, "InfraDevice", uuid_identifier, schema=pre_fetched_schema)

    assert result is expected_node
    mock_client.schema.get.assert_not_awaited()


async def test_resolve_default_filter_miss_falls_through_to_hfid(mock_client: MagicMock) -> None:
    """When the default-filter lookup returns ``None``, the HFID strategy is tried next."""
    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = "name__value"
    mock_schema.human_friendly_id = ["name__value"]
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    # First call (default_filter) returns None; second call (hfid) returns the node.
    mock_client.get = AsyncMock(side_effect=[None, expected_node])

    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False):
        result = await resolve_node(mock_client, "InfraDevice", "router1")

    assert result is expected_node
    assert mock_client.get.await_count == 2


# --- Tests for prepare_relationship_data ---


def _make_schema(attribute_names: list[str], relationship_names: list[str]) -> MagicMock:
    schema = MagicMock()
    schema.attribute_names = attribute_names
    schema.relationship_names = relationship_names
    return schema


def test_prepare_relationship_data_attributes_unchanged() -> None:
    """Attribute values pass through without modification."""
    schema = _make_schema(["name", "description"], ["site"])
    data = {"name": "router1", "description": "core router"}
    result = prepare_relationship_data(data, schema)
    assert result == {"name": "router1", "description": "core router"}


def test_prepare_relationship_data_uuid_passthrough() -> None:
    """UUID relationship values pass through as strings."""
    schema = _make_schema([], ["site"])
    data = {"site": "12345678-1234-5678-1234-567812345678"}
    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=True):
        result = prepare_relationship_data(data, schema)
    assert result == {"site": "12345678-1234-5678-1234-567812345678"}


def test_prepare_relationship_data_hfid_single() -> None:
    """Non-UUID string is converted to a single-component HFID list."""
    schema = _make_schema([], ["site"])
    data = {"site": "DC1"}
    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False):
        result = prepare_relationship_data(data, schema)
    assert result == {"site": ["DC1"]}


def test_prepare_relationship_data_hfid_multi_component() -> None:
    """Multi-component HFID string is split on /."""
    schema = _make_schema([], ["platform"])
    data = {"platform": "Cisco/NX-OS"}
    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False):
        result = prepare_relationship_data(data, schema)
    assert result == {"platform": ["Cisco", "NX-OS"]}


def test_prepare_relationship_data_list_passthrough() -> None:
    """List values (cardinality-many) pass through unchanged."""
    schema = _make_schema([], ["tags"])
    data = {"tags": [["blue"], ["red"]]}
    result = prepare_relationship_data(data, schema)
    assert result == {"tags": [["blue"], ["red"]]}


def test_prepare_relationship_data_dict_passthrough() -> None:
    """Dict values (already structured) pass through unchanged."""
    schema = _make_schema([], ["site"])
    data = {"site": {"id": "some-uuid"}}
    result = prepare_relationship_data(data, schema)
    assert result == {"site": {"id": "some-uuid"}}


def test_prepare_relationship_data_mixed() -> None:
    """Mixed attributes and relationships are handled correctly."""
    schema = _make_schema(["name"], ["site", "tags"])
    data = {"name": "router1", "site": "DC1", "tags": [["blue"]]}
    with patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False):
        result = prepare_relationship_data(data, schema)
    assert result == {"name": "router1", "site": ["DC1"], "tags": [["blue"]]}


def _pool_schema(relationship: dict[str, Any]) -> NodeSchemaAPI:
    data: dict[str, Any] = {
        "name": "NumberPool",
        "namespace": "Core",
        "attributes": [{"name": "name", "kind": "Text", "unique": True}],
        "relationships": [relationship],
    }
    return NodeSchema(**data).convert_api()


CREATE_REFUSAL = re.escape(
    "'ranges' cannot be set with --set to a reference, because the mutation takes the fields of a "
    "CoreNumberPoolRange and not a reference to one. Pass the fields of every CoreNumberPoolRange "
    "instead, as a JSON list of objects."
)

UPDATE_REFUSAL = re.escape(
    "'ranges' cannot be changed with --set, because the mutation takes the fields of a CoreNumberPoolRange "
    "and not a reference to one. To set the complete list, run infrahubctl object create with it, which "
    "upserts the node. To add, change or delete one, run infrahubctl object create, update or delete on the "
    "CoreNumberPoolRange node itself."
)


def _ranges_schema() -> NodeSchemaAPI:
    return _pool_schema(
        {"name": "ranges", "peer": "CoreNumberPoolRange", "cardinality": "many", "identifier": "numberpool__range"}
    )


def _allowed_ranges_schema() -> NodeSchemaAPI:
    return _pool_schema(
        {
            "name": "allowed_ranges",
            "peer": "CoreNumberPoolRange",
            "cardinality": "many",
            "identifier": "numberpool__allowed_range",
        }
    )


@dataclass
class ReferenceCase:
    name: str
    value: Any


REFERENCE_CASES = [
    ReferenceCase(name="single-hfid", value="range-1"),
    ReferenceCase(name="list-of-hfids", value=["range-1", "range-2"]),
    ReferenceCase(name="list-of-hfid-parts", value=[["Core", "range-1"]]),
    ReferenceCase(name="uuid", value="550e8400-e29b-41d4-a716-446655440000"),
    ReferenceCase(name="object-holding-an-id", value=[{"id": "550e8400-e29b-41d4-a716-446655440000"}]),
    ReferenceCase(name="object-holding-an-hfid", value=[{"hfid": ["range-1"]}]),
    ReferenceCase(name="object-holding-a-node", value=[{"node": {"start": 1}}]),
    ReferenceCase(name="fields-and-a-reference", value=[{"start": 1, "end": 10}, {"id": "range-2"}]),
]

FIELDS_CASES = [
    ReferenceCase(name="one-range", value=[{"start": 1, "end": 10}]),
    ReferenceCase(name="two-ranges", value=[{"start": 1, "end": 10}, {"start": 20}]),
    ReferenceCase(name="no-range", value=[]),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in REFERENCE_CASES])
def test_create_refuses_a_reference_to_a_peer_the_mutation_takes_as_fields(case: ReferenceCase) -> None:
    """The reference never reaches Infrahub, so the command says so instead of sending it."""
    with pytest.raises(FeatureNotSupportedError, match=CREATE_REFUSAL):
        raise_if_set_names_inline_peers_by_reference({"name": "VLAN IDs", "ranges": case.value}, _ranges_schema())


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in FIELDS_CASES])
def test_create_takes_the_fields_of_the_peers(case: ReferenceCase) -> None:
    """The fields are what the mutation takes, so --set carries them as they are."""
    raise_if_set_names_inline_peers_by_reference({"name": "VLAN IDs", "ranges": case.value}, _ranges_schema())


def test_create_takes_a_reference_for_another_relationship_to_the_same_peer() -> None:
    """Only the relationship Infrahub takes as fields is concerned, not every relationship to a range."""
    raise_if_set_names_inline_peers_by_reference({"allowed_ranges": "range-1"}, _allowed_ranges_schema())


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in REFERENCE_CASES + FIELDS_CASES])
def test_update_refuses_every_value_for_such_a_relationship(case: ReferenceCase) -> None:
    """An update sends the peers the node was fetched with, so any value given here is dropped."""
    with pytest.raises(FeatureNotSupportedError, match=UPDATE_REFUSAL):
        raise_if_set_edits_inline_peers({"name": "VLAN IDs", "ranges": case.value}, _ranges_schema())


def test_update_takes_another_relationship_to_the_same_peer() -> None:
    raise_if_set_edits_inline_peers({"allowed_ranges": "range-1"}, _allowed_ranges_schema())


def test_neither_guard_reads_the_schema_of_an_attribute() -> None:
    """An attribute has no relationship schema to read, and asking for one raises."""
    schema = _ranges_schema()

    raise_if_set_names_inline_peers_by_reference({"name": "VLAN IDs"}, schema)
    raise_if_set_edits_inline_peers({"name": "VLAN IDs"}, schema)
