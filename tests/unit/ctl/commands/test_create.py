"""Unit tests for the ``infrahub create`` end-user CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from infrahub_sdk.ctl.enduser_cli import app

runner = CliRunner()


def test_create_help() -> None:
    """``create --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["create", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout


def test_create_mutual_exclusivity() -> None:
    """Passing both --set and --file exits with a non-zero code."""
    result = runner.invoke(app, ["create", "InfraDevice", "--set", "name=router1", "--file", "objects.yml"])
    assert result.exit_code != 0


def test_create_no_args() -> None:
    """Omitting both --set and --file exits with a non-zero code."""
    result = runner.invoke(app, ["create", "InfraDevice"])
    assert result.exit_code != 0
