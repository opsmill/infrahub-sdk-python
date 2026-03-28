"""Unit tests for the ``infrahub get`` end-user CLI command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app

runner = CliRunner()


def test_get_help() -> None:
    """``get --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["get", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout


def test_get_list_mode() -> None:
    """List mode calls ``client.filters`` and prints node data."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name", "description"]
    mock_schema.relationship_names = []

    mock_node = MagicMock()
    mock_node.id = "abc-123"
    mock_node.display_label = "test-device"

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)
    mock_client.filters = AsyncMock(return_value=[mock_node])

    mock_formatter = MagicMock()
    mock_formatter.format_list.return_value = "device-list-output"

    with (
        patch("infrahub_sdk.ctl.commands.get.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.commands.get.detect_output_format", return_value="json"),
        patch("infrahub_sdk.ctl.commands.get.get_formatter", return_value=mock_formatter),
    ):
        result = runner.invoke(app, ["get", "InfraDevice"])

    assert result.exit_code == 0
    mock_client.schema.get.assert_awaited_once_with(kind="InfraDevice", branch=None)
    mock_client.filters.assert_awaited_once()
    mock_formatter.format_list.assert_called_once_with([mock_node], mock_schema, show_all_columns=False)


def test_get_detail_mode() -> None:
    """Detail mode calls ``client.get`` when an identifier is supplied."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name"]
    mock_schema.relationship_names = []

    mock_node = MagicMock()
    mock_node.id = "abc-123"
    mock_node.display_label = "test-device"

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)
    mock_client.get = AsyncMock(return_value=mock_node)

    mock_formatter = MagicMock()
    mock_formatter.format_detail.return_value = '{"id": "abc-123"}'

    with (
        patch("infrahub_sdk.ctl.commands.get.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.commands.get.detect_output_format", return_value="json"),
        patch("infrahub_sdk.ctl.commands.get.get_formatter", return_value=mock_formatter),
    ):
        result = runner.invoke(app, ["get", "InfraDevice", "abc-123"])

    assert result.exit_code == 0
    mock_client.get.assert_awaited_once_with(kind="InfraDevice", id="abc-123")
    mock_formatter.format_detail.assert_called_once_with(mock_node, mock_schema)


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--branch", "my-branch"],
        ["--limit", "10"],
        ["--offset", "5"],
        ["--filter", "name__value=router1"],
    ],
)
def test_get_list_mode_with_options(extra_args: list[str]) -> None:
    """List mode accepts optional flags without error."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = []
    mock_schema.relationship_names = []

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)
    mock_client.filters = AsyncMock(return_value=[])

    mock_formatter = MagicMock()
    mock_formatter.format_list.return_value = "[]"

    with (
        patch("infrahub_sdk.ctl.commands.get.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.commands.get.detect_output_format", return_value="json"),
        patch("infrahub_sdk.ctl.commands.get.get_formatter", return_value=mock_formatter),
    ):
        result = runner.invoke(app, ["get", "InfraDevice", *extra_args])

    # Exit 80 = query succeeded but no results (empty mock)
    assert result.exit_code == 80
