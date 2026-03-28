"""Unit tests for the ``infrahub delete`` end-user CLI command."""

from __future__ import annotations

from typer.testing import CliRunner

from infrahub_sdk.ctl.enduser_cli import app

runner = CliRunner()


def test_delete_help() -> None:
    """``delete --help`` exits cleanly and includes usage text."""
    result = runner.invoke(app, ["delete", "--help"])
    assert result.exit_code == 0
    assert "kind" in result.stdout.lower() or "Usage" in result.stdout
