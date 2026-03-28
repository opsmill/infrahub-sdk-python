"""Unit tests for the ``infrahub schema`` end-user CLI subcommand group."""

from __future__ import annotations

from typer.testing import CliRunner

from infrahub_sdk.ctl.enduser_cli import app

runner = CliRunner()


def test_schema_list_help() -> None:
    """``schema list --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["schema", "list", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_schema_show_help() -> None:
    """``schema show --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["schema", "show", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout
