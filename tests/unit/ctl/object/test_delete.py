"""Unit tests for the ``infrahub object delete`` end-user CLI command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app

runner = CliRunner()


def test_delete_help() -> None:
    """``object delete --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["object", "delete", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout


def test_delete_with_yes() -> None:
    """``object delete --yes`` skips confirmation, deletes the node, and prints a confirmation."""
    mock_node = MagicMock()
    mock_node.id = "node-del-001"
    mock_node.display_label = "router-to-delete"
    mock_node.delete = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.delete.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.object.delete.resolve_node", new_callable=AsyncMock, return_value=mock_node),
    ):
        result = runner.invoke(app, ["object", "delete", "InfraDevice", "node-del-001", "--yes"])

    assert result.exit_code == 0, result.stdout
    assert "Deleted" in result.stdout
    mock_node.delete.assert_awaited_once()


def test_delete_with_yes_short_flag() -> None:
    """``object delete -y`` is equivalent to ``--yes``."""
    mock_node = MagicMock()
    mock_node.id = "node-del-002"
    mock_node.display_label = "router-b"
    mock_node.delete = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.delete.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.object.delete.resolve_node", new_callable=AsyncMock, return_value=mock_node),
    ):
        result = runner.invoke(app, ["object", "delete", "InfraDevice", "node-del-002", "-y"])

    assert result.exit_code == 0, result.stdout
    mock_node.delete.assert_awaited_once()


def test_delete_with_branch() -> None:
    """``object delete`` forwards --branch to initialize_client."""
    mock_node = MagicMock()
    mock_node.id = "node-br-del"
    mock_node.display_label = "device-in-branch"
    mock_node.delete = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.delete.initialize_client", return_value=mock_client) as mock_init,
        patch("infrahub_sdk.ctl.object.delete.resolve_node", new_callable=AsyncMock, return_value=mock_node),
    ):
        result = runner.invoke(
            app,
            ["object", "delete", "InfraDevice", "node-br-del", "--yes", "--branch", "my-branch"],
        )

    assert result.exit_code == 0, result.stdout
    mock_init.assert_called_once_with(branch="my-branch")
    mock_node.delete.assert_awaited_once()


def test_delete_confirmation_abort() -> None:
    """Answering ``n`` at the confirmation prompt aborts deletion without calling delete."""
    mock_node = MagicMock()
    mock_node.id = "node-abort"
    mock_node.display_label = "router-keep"
    mock_node.delete = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.delete.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.object.delete.resolve_node", new_callable=AsyncMock, return_value=mock_node),
    ):
        result = runner.invoke(app, ["object", "delete", "InfraDevice", "node-abort"], input="n\n")

    assert result.exit_code != 0
    mock_node.delete.assert_not_awaited()


def test_delete_confirmation_yes_input() -> None:
    """Answering ``y`` at the confirmation prompt proceeds with deletion."""
    mock_node = MagicMock()
    mock_node.id = "node-confirm"
    mock_node.display_label = "router-confirm"
    mock_node.delete = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.delete.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.object.delete.resolve_node", new_callable=AsyncMock, return_value=mock_node),
    ):
        result = runner.invoke(app, ["object", "delete", "InfraDevice", "node-confirm"], input="y\n")

    assert result.exit_code == 0, result.stdout
    assert "Deleted" in result.stdout
    mock_node.delete.assert_awaited_once()


def test_delete_output_contains_id_and_label() -> None:
    """Deletion confirmation message includes the node ID and display label."""
    mock_node = MagicMock()
    mock_node.id = "unique-id-xyz"
    mock_node.display_label = "specific-router"
    mock_node.delete = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.delete.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.object.delete.resolve_node", new_callable=AsyncMock, return_value=mock_node),
    ):
        result = runner.invoke(app, ["object", "delete", "InfraDevice", "unique-id-xyz", "--yes"])

    assert result.exit_code == 0, result.stdout
    assert "unique-id-xyz" in result.stdout
    assert "specific-router" in result.stdout
