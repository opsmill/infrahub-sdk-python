"""Unit tests for the ``infrahub update`` end-user CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from infrahub_sdk.ctl.enduser_cli import app

runner = CliRunner()


def test_update_help() -> None:
    """``update --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["update", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout


def test_update_mutual_exclusivity() -> None:
    """Passing both --set and --file exits with a non-zero code."""
    result = runner.invoke(
        app,
        ["update", "InfraDevice", "abc-123", "--set", "name=router1", "--file", "objects.yml"],
    )
    assert result.exit_code != 0


def test_update_no_args() -> None:
    """Omitting both --set and --file exits with a non-zero code."""
    result = runner.invoke(app, ["update", "InfraDevice", "abc-123"])
    assert result.exit_code != 0
