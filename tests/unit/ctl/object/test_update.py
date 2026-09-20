"""Unit tests for the ``infrahub object update`` end-user CLI command."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli_commands import app

runner = CliRunner()


def test_update_help() -> None:
    """``object update --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["object", "update", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout


def test_update_mutual_exclusivity() -> None:
    """Passing both --set and --file exits with a non-zero code."""
    result = runner.invoke(
        app,
        ["object", "update", "InfraDevice", "abc-123", "--set", "name=router1", "--file", "objects.yml"],
    )
    assert result.exit_code != 0


def test_update_no_args() -> None:
    """Omitting both --set and --file exits with a non-zero code."""
    result = runner.invoke(app, ["object", "update", "InfraDevice", "abc-123"])
    assert result.exit_code != 0


def test_update_with_set_args() -> None:
    """``object update`` with --set fetches the node, applies the change, and saves it."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name", "description"]
    mock_schema.relationship_names = []
    mock_schema.get_attribute = lambda _name: SimpleNamespace(read_only=False)

    mock_attr = MagicMock()
    mock_attr.value = "old-name"

    mock_node = MagicMock()
    mock_node.id = "abc-123"
    mock_node.display_label = "router1"
    mock_node.name = mock_attr
    mock_node.save = AsyncMock()

    def getattr_side_effect(obj: object, name: str) -> MagicMock:
        if name == "name":
            return mock_attr
        return MagicMock()

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.object.update.getattr", side_effect=getattr_side_effect, create=True),
        patch(
            "infrahub_sdk.ctl.object.update.resolve_node",
            new_callable=AsyncMock,
            return_value=mock_node,
        ) as mock_resolve,
    ):
        result = runner.invoke(app, ["object", "update", "InfraDevice", "abc-123", "--set", "name=router1"])

    assert result.exit_code == 0, result.stdout
    assert "Updated" in result.stdout
    mock_client.schema.get.assert_awaited_once_with(kind="InfraDevice", branch=None)
    mock_resolve.assert_awaited_once_with(mock_client, "InfraDevice", "abc-123", schema=mock_schema, branch=None)
    mock_node.save.assert_awaited_once()


def test_update_with_set_args_attribute_applied() -> None:
    """``object update`` with an attribute --set updates the attribute value on the node."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["description"]
    mock_schema.relationship_names = []
    mock_schema.get_attribute = lambda _name: SimpleNamespace(read_only=False)

    mock_attr = MagicMock()
    mock_attr.value = "old description"

    mock_node = MagicMock()
    mock_node.id = "node-001"
    mock_node.display_label = "device-a"
    mock_node.save = AsyncMock()

    mock_node.description = mock_attr

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.update.resolve_node",
            new_callable=AsyncMock,
            return_value=mock_node,
        ),
    ):
        result = runner.invoke(
            app, ["object", "update", "InfraDevice", "node-001", "--set", "description=new description"]
        )

    assert result.exit_code == 0, result.stdout
    assert "Updated" in result.stdout
    mock_node.save.assert_awaited_once()


def test_update_with_set_args_and_branch() -> None:
    """``object update`` forwards --branch to schema and resolve_node calls."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name"]
    mock_schema.relationship_names = []
    mock_schema.get_attribute = lambda _name: SimpleNamespace(read_only=False)

    mock_attr = MagicMock()
    mock_attr.value = "old"

    mock_node = MagicMock()
    mock_node.id = "node-br"
    mock_node.display_label = "device-br"
    mock_node.save = AsyncMock()

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.update.resolve_node",
            new_callable=AsyncMock,
            return_value=mock_node,
        ) as mock_resolve,
    ):
        result = runner.invoke(
            app,
            ["object", "update", "InfraDevice", "node-br", "--set", "name=newname", "--branch", "feature-x"],
        )

    assert result.exit_code == 0, result.stdout
    mock_client.schema.get.assert_awaited_once_with(kind="InfraDevice", branch="feature-x")
    mock_resolve.assert_awaited_once_with(mock_client, "InfraDevice", "node-br", schema=mock_schema, branch="feature-x")


def test_update_invalid_field() -> None:
    """Using --set with an unknown field name exits with a non-zero code."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["name"]
    mock_schema.relationship_names = []

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.object.update.resolve_node", new_callable=AsyncMock),
    ):
        result = runner.invoke(app, ["object", "update", "InfraDevice", "abc-123", "--set", "unknown_field=value"])

    assert result.exit_code != 0


def test_update_read_only_field_rejected() -> None:
    """Using --set on a read-only attribute exits non-zero before resolving the node."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["computed_address"]
    mock_schema.relationship_names = []
    mock_schema.get_attribute = lambda _name: SimpleNamespace(read_only=True)

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    mock_resolve = AsyncMock()
    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch("infrahub_sdk.ctl.object.update.resolve_node", mock_resolve),
    ):
        result = runner.invoke(app, ["object", "update", "InfraDevice", "abc-123", "--set", "computed_address=x"])

    assert result.exit_code != 0
    assert "read-only" in result.stdout
    assert "computed_address" in result.stdout
    # rejected during validation, before the node is fetched or mutated
    mock_resolve.assert_not_awaited()


def test_update_with_file() -> None:
    """``object update`` with --file delegates to ObjectFile and prints a confirmation."""
    mock_file = MagicMock()
    mock_file.validate_format = AsyncMock()
    mock_file.process = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.update.ObjectFile.load_from_disk",
            return_value=[mock_file],
        ),
    ):
        result = runner.invoke(app, ["object", "update", "InfraDevice", "abc-123", "--file", "updates.yml"])

    assert result.exit_code == 0, result.stdout
    assert "Processed" in result.stdout or "successfully" in result.stdout.lower()
    mock_file.validate_format.assert_awaited_once_with(client=mock_client, branch=None)
    mock_file.process.assert_awaited_once_with(client=mock_client, branch=None)


def test_update_with_file_and_branch() -> None:
    """``object update`` with --file forwards --branch to validate_format and process."""
    mock_file = MagicMock()
    mock_file.validate_format = AsyncMock()
    mock_file.process = AsyncMock()

    mock_client = MagicMock()

    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.update.ObjectFile.load_from_disk",
            return_value=[mock_file],
        ),
    ):
        result = runner.invoke(
            app,
            ["object", "update", "InfraDevice", "abc-123", "--file", "updates.yml", "--branch", "staging"],
        )

    assert result.exit_code == 0, result.stdout
    mock_file.validate_format.assert_awaited_once_with(client=mock_client, branch="staging")
    mock_file.process.assert_awaited_once_with(client=mock_client, branch="staging")


def test_update_with_set_args_relationship() -> None:
    """``object update`` with a relationship --set converts to HFID and saves."""
    mock_rel_schema = MagicMock()
    mock_rel_schema.cardinality = "one"
    mock_rel_schema.name = "site"

    mock_schema = MagicMock()
    mock_schema.attribute_names = []
    mock_schema.relationship_names = ["site"]
    mock_schema.get_relationship = MagicMock(return_value=mock_rel_schema)

    mock_node = MagicMock()
    mock_node.id = "node-rel-001"
    mock_node.display_label = "device-rel"
    mock_node.save = AsyncMock()

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.update.resolve_node",
            new_callable=AsyncMock,
            return_value=mock_node,
        ),
    ):
        result = runner.invoke(app, ["object", "update", "InfraDevice", "node-rel-001", "--set", "site=DC1"])

    assert result.exit_code == 0, result.stdout
    assert "Updated" in result.stdout
    mock_node.save.assert_awaited_once()


def test_update_with_set_args_attribute_noop() -> None:
    """``object update`` with only attribute --set that matches existing value is a no-op."""
    mock_schema = MagicMock()
    mock_schema.attribute_names = ["description"]
    mock_schema.relationship_names = []
    mock_schema.get_attribute = lambda _name: SimpleNamespace(read_only=False)

    mock_attr = MagicMock()
    mock_attr.value = "same value"

    mock_node = MagicMock()
    mock_node.id = "node-noop-001"
    mock_node.display_label = "device-noop"
    mock_node.save = AsyncMock()

    mock_node.description = mock_attr

    mock_client = MagicMock()
    mock_client.schema = MagicMock()
    mock_client.schema.get = AsyncMock(return_value=mock_schema)

    with (
        patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client),
        patch(
            "infrahub_sdk.ctl.object.update.resolve_node",
            new_callable=AsyncMock,
            return_value=mock_node,
        ),
    ):
        result = runner.invoke(
            app, ["object", "update", "InfraDevice", "node-noop-001", "--set", "description=same value"]
        )

    assert result.exit_code == 0, result.stdout
    assert "No changes" in result.stdout
    mock_node.save.assert_not_awaited()


@pytest.mark.parametrize("bad_arg", ["noequals", "=emptykey"])
def test_update_malformed_set_arg(bad_arg: str) -> None:
    """Malformed --set arguments (no ``=`` or empty key) exit with a non-zero code."""
    mock_client = MagicMock()

    with patch("infrahub_sdk.ctl.object.update.initialize_client", return_value=mock_client):
        result = runner.invoke(app, ["object", "update", "InfraDevice", "abc-123", "--set", bad_arg])

    assert result.exit_code != 0
