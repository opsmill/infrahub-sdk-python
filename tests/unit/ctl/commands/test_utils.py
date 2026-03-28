"""Unit tests for ``infrahub_sdk.ctl.commands.utils``."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrahub_sdk.ctl.commands.utils import resolve_node
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


@pytest.mark.anyio
async def test_resolve_by_uuid(mock_client: MagicMock) -> None:
    """When the identifier is a valid UUID, ``client.get(id=...)`` is called directly."""
    mock_schema = MagicMock()
    mock_schema.default_filter = None
    mock_schema.human_friendly_id = None
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    uuid_identifier = "12345678-1234-5678-1234-567812345678"

    with patch("infrahub_sdk.ctl.commands.utils.is_valid_uuid", return_value=True):
        result = await resolve_node(mock_client, "InfraDevice", uuid_identifier)

    assert result is expected_node
    mock_client.get.assert_awaited_once_with(kind="InfraDevice", id=uuid_identifier, branch=None)


@pytest.mark.anyio
async def test_resolve_by_default_filter(mock_client: MagicMock) -> None:
    """When the schema has a ``default_filter``, it is used as a keyword filter."""
    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = "name__value"
    mock_schema.human_friendly_id = None
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    with patch("infrahub_sdk.ctl.commands.utils.is_valid_uuid", return_value=False):
        result = await resolve_node(mock_client, "InfraDevice", "router1")

    assert result is expected_node
    mock_client.get.assert_awaited_once_with(
        kind="InfraDevice",
        branch=None,
        raise_when_missing=False,
        name__value="router1",
    )


@pytest.mark.anyio
async def test_resolve_by_hfid(mock_client: MagicMock) -> None:
    """When the schema defines ``human_friendly_id``, ``client.get(hfid=...)`` is used."""

    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = None
    mock_schema.human_friendly_id = ["name__value"]
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    with patch("infrahub_sdk.ctl.commands.utils.is_valid_uuid", return_value=False):
        result = await resolve_node(mock_client, "InfraDevice", "router1")

    assert result is expected_node
    mock_client.get.assert_awaited_once_with(
        kind="InfraDevice",
        hfid=["router1"],
        branch=None,
        raise_when_missing=False,
    )


@pytest.mark.anyio
async def test_resolve_by_hfid_multi_component(mock_client: MagicMock) -> None:
    """Multi-component HFID strings (``a/b``) are split on ``/``."""

    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = None
    mock_schema.human_friendly_id = ["site__name__value", "name__value"]
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    with patch("infrahub_sdk.ctl.commands.utils.is_valid_uuid", return_value=False):
        result = await resolve_node(mock_client, "InfraDevice", "london/router1")

    assert result is expected_node
    mock_client.get.assert_awaited_once_with(
        kind="InfraDevice",
        hfid=["london", "router1"],
        branch=None,
        raise_when_missing=False,
    )


@pytest.mark.anyio
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
        patch("infrahub_sdk.ctl.commands.utils.is_valid_uuid", return_value=False),
        pytest.raises(NodeNotFoundError),
    ):
        await resolve_node(mock_client, "InfraDevice", "unknown-name")

    mock_client.get.assert_awaited_once_with(kind="InfraDevice", id="unknown-name", branch=None)


@pytest.mark.anyio
async def test_resolve_uses_provided_schema(mock_client: MagicMock) -> None:
    """When ``schema`` is provided, ``client.schema.get`` is not called."""
    pre_fetched_schema = MagicMock(spec=NodeSchemaAPI)
    pre_fetched_schema.default_filter = None
    pre_fetched_schema.human_friendly_id = None

    expected_node = MagicMock()
    mock_client.get = AsyncMock(return_value=expected_node)

    uuid_identifier = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with patch("infrahub_sdk.ctl.commands.utils.is_valid_uuid", return_value=True):
        result = await resolve_node(mock_client, "InfraDevice", uuid_identifier, schema=pre_fetched_schema)

    assert result is expected_node
    mock_client.schema.get.assert_not_awaited()


@pytest.mark.anyio
async def test_resolve_default_filter_miss_falls_through_to_hfid(mock_client: MagicMock) -> None:
    """When the default-filter lookup returns ``None``, the HFID strategy is tried next."""
    mock_schema = MagicMock(spec=NodeSchemaAPI)
    mock_schema.default_filter = "name__value"
    mock_schema.human_friendly_id = ["name__value"]
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    expected_node = MagicMock()
    # First call (default_filter) returns None; second call (hfid) returns the node.
    mock_client.get = AsyncMock(side_effect=[None, expected_node])

    with patch("infrahub_sdk.ctl.commands.utils.is_valid_uuid", return_value=False):
        result = await resolve_node(mock_client, "InfraDevice", "router1")

    assert result is expected_node
    assert mock_client.get.await_count == 2
