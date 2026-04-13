"""Unit tests for ``infrahub_sdk.ctl.object.utils``."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrahub_sdk.ctl.object.utils import derive_identifier, prepare_relationship_data, resolve_node
from infrahub_sdk.exceptions import NodeNotFoundError
from infrahub_sdk.schema import NodeSchemaAPI


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
    """When no lookup strategy matches, the fallback ``client.get(id=...)`` call raises."""

    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = None
    mock_schema.human_friendly_id = None
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    mock_client.get = AsyncMock(
        side_effect=NodeNotFoundError(identifier={"id": ["unknown-name"]}, node_type="InfraDevice")
    )

    with (
        patch("infrahub_sdk.ctl.object.utils.is_valid_uuid", return_value=False),
        pytest.raises(NodeNotFoundError),
    ):
        await resolve_node(mock_client, "InfraDevice", "unknown-name")

    mock_client.get.assert_awaited_once_with(kind="InfraDevice", id="unknown-name", branch=None)


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


# --- Tests for derive_identifier ---


def test_derive_identifier_from_hfid() -> None:
    """HFID components are assembled from data fields and joined with /."""
    schema = MagicMock(spec=NodeSchemaAPI)
    schema.human_friendly_id = ["site__name__value", "name__value"]
    schema.default_filter = None
    data = {"site": "DC1", "name": "router1"}
    assert derive_identifier(data, schema) == "DC1/router1"


def test_derive_identifier_from_hfid_partial() -> None:
    """Partial HFID (missing component) falls through to default_filter."""
    schema = MagicMock(spec=NodeSchemaAPI)
    schema.human_friendly_id = ["site__name__value", "name__value"]
    schema.default_filter = "name__value"
    data = {"name": "router1"}
    assert derive_identifier(data, schema) == "router1"


def test_derive_identifier_from_default_filter() -> None:
    """default_filter field is used when HFID is not defined."""
    schema = MagicMock(spec=NodeSchemaAPI)
    schema.human_friendly_id = None
    schema.default_filter = "prefix__value"
    data = {"prefix": "10.0.0.0/8"}
    assert derive_identifier(data, schema) == "10.0.0.0/8"


def test_derive_identifier_fallback_to_name() -> None:
    """Falls back to 'name' field when no schema hints are available."""
    schema = MagicMock()
    data = {"name": "router1", "description": "core"}
    assert derive_identifier(data, schema) == "router1"


def test_derive_identifier_returns_none() -> None:
    """Returns None when no identifier can be derived."""
    schema = MagicMock()
    data = {"description": "core"}
    assert derive_identifier(data, schema) is None
