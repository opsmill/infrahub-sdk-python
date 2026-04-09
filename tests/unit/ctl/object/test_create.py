"""Unit tests for the ``infrahub object create`` end-user CLI command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app
from infrahub_sdk.exceptions import NodeNotFoundError

runner = CliRunner()


def test_create_help() -> None:
    """``object create --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["object", "create", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout


def test_create_mutual_exclusivity() -> None:
    """Passing both --set and --file exits with a non-zero code."""
    result = runner.invoke(app, ["object", "create", "InfraDevice", "--set", "name=router1", "--file", "objects.yml"])
    assert result.exit_code != 0


def test_create_no_args() -> None:
    """Omitting both --set and --file exits with a non-zero code."""
    result = runner.invoke(app, ["object", "create", "InfraDevice"])
    assert result.exit_code != 0


def test_create_with_set_args() -> None:
    """``object create`` with --set creates a node and prints a confirmation."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name", "description"]
    mock_schema.relationship_names = ["site"]

    mock_node = MagicMock()
    mock_node.id = "test-id-001"
    mock_node.display_label = "router1"
    mock_node.save = AsyncMock()

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)
    mock_client.create = AsyncMock(return_value=mock_node)

    with (
        patch("infrahub_sdk.ctl.object.create.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.create.resolve_node",
            new_callable=AsyncMock,
            side_effect=NodeNotFoundError(identifier={"name": ["router1"]}),
        ),
    ):
        result = runner.invoke(app, ["object", "create", "InfraDevice", "--set", "name=router1"])

    assert result.exit_code == 0, result.stdout
    assert "Created" in result.stdout
    mock_client.schema.get.assert_awaited_once_with(kind="InfraDevice", branch=None)
    mock_client.create.assert_awaited_once_with(kind="InfraDevice", data={"name": "router1"}, branch=None)
    mock_node.save.assert_awaited_once_with(allow_upsert=True)


def test_create_with_set_args_and_branch() -> None:
    """``object create`` forwards --branch to client calls."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name"]
    mock_schema.relationship_names = []

    mock_node = MagicMock()
    mock_node.id = "test-id-002"
    mock_node.display_label = "router2"
    mock_node.save = AsyncMock()

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)
    mock_client.create = AsyncMock(return_value=mock_node)

    with (
        patch("infrahub_sdk.ctl.object.create.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.create.resolve_node",
            new_callable=AsyncMock,
            side_effect=NodeNotFoundError(identifier={"name": ["router2"]}),
        ),
    ):
        result = runner.invoke(
            app,
            ["object", "create", "InfraDevice", "--set", "name=router2", "--branch", "dev"],
        )

    assert result.exit_code == 0, result.stdout
    mock_client.schema.get.assert_awaited_once_with(kind="InfraDevice", branch="dev")
    mock_client.create.assert_awaited_once_with(kind="InfraDevice", data={"name": "router2"}, branch="dev")


def test_create_with_file() -> None:
    """``object create`` with --file delegates to ObjectFile and prints a confirmation."""
    mock_file = MagicMock()
    mock_file.spec.data = [{"name": "router-a"}, {"name": "router-b"}]
    mock_file.spec.kind = "InfraDevice"
    mock_file.validate_format = AsyncMock()
    mock_file.process = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.create.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.create.ObjectFile.load_from_disk",
            return_value=[mock_file],
        ),
    ):
        result = runner.invoke(app, ["object", "create", "InfraDevice", "--file", "devices.yml"])

    assert result.exit_code == 0, result.stdout
    assert "Created" in result.stdout
    assert "2" in result.stdout
    assert "InfraDevice" in result.stdout
    mock_file.validate_format.assert_awaited_once_with(client=mock_client, branch=None)
    mock_file.process.assert_awaited_once_with(client=mock_client, branch=None)


def test_create_with_file_multiple_files() -> None:
    """``object create`` with --file processes every file returned by load_from_disk."""

    def make_obj_file(kind: str, count: int) -> MagicMock:
        obj = MagicMock()
        obj.spec.data = [{"name": f"item-{i}"} for i in range(count)]
        obj.spec.kind = kind
        obj.validate_format = AsyncMock()
        obj.process = AsyncMock()
        return obj

    file_a = make_obj_file("InfraDevice", 2)
    file_b = make_obj_file("InfraDevice", 3)

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.create.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.create.ObjectFile.load_from_disk",
            return_value=[file_a, file_b],
        ),
    ):
        result = runner.invoke(app, ["object", "create", "InfraDevice", "--file", "multi.yml"])

    assert result.exit_code == 0, result.stdout
    file_a.validate_format.assert_awaited_once()
    file_a.process.assert_awaited_once()
    file_b.validate_format.assert_awaited_once()
    file_b.process.assert_awaited_once()


def test_create_with_file_kind_mismatch() -> None:
    """``object create`` with --file rejects files whose kind doesn't match the positional kind."""
    mock_file = MagicMock()
    mock_file.spec.data = [{"name": "item-0"}]
    mock_file.spec.kind = "InfraPrefix"
    mock_file.validate_format = AsyncMock()
    mock_file.process = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.create.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.create.ObjectFile.load_from_disk",
            return_value=[mock_file],
        ),
    ):
        result = runner.invoke(app, ["object", "create", "InfraDevice", "--file", "prefix.yml"])

    assert result.exit_code != 0
    assert "does not match" in result.stdout


def test_create_invalid_field() -> None:
    """Using --set with an unknown field name exits with a non-zero code."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name", "description"]
    mock_schema.relationship_names = ["site"]

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    with patch("infrahub_sdk.ctl.object.create.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["object", "create", "InfraDevice", "--set", "nonexistent_field=value"])

    assert result.exit_code != 0


def test_create_multiple_set_args() -> None:
    """``object create`` accepts multiple --set options and passes all fields to the client."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name", "description"]
    mock_schema.relationship_names = []

    mock_node = MagicMock()
    mock_node.id = "test-id-003"
    mock_node.display_label = "router3"
    mock_node.save = AsyncMock()

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)
    mock_client.create = AsyncMock(return_value=mock_node)

    with (
        patch("infrahub_sdk.ctl.object.create.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.create.resolve_node",
            new_callable=AsyncMock,
            side_effect=NodeNotFoundError(identifier={"name": ["router3"]}),
        ),
    ):
        result = runner.invoke(
            app,
            ["object", "create", "InfraDevice", "--set", "name=router3", "--set", "description=core router"],
        )

    assert result.exit_code == 0, result.stdout
    _, call_kwargs = mock_client.create.call_args
    assert call_kwargs["data"] == {"name": "router3", "description": "core router"}


@pytest.mark.parametrize("bad_arg", ["noequals", "=emptykey"])
def test_create_malformed_set_arg(bad_arg: str) -> None:
    """Malformed --set arguments (no ``=`` or empty key) exit with a non-zero code."""
    mock_client = MagicMock()

    with patch("infrahub_sdk.ctl.object.create.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["object", "create", "InfraDevice", "--set", bad_arg])

    assert result.exit_code != 0
