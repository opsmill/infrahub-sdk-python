import sys

import pytest
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli import app

runner = CliRunner()

requires_python_310 = pytest.mark.skipif(sys.version_info < (3, 10), reason="Requires Python 3.10 or higher")


@requires_python_310
def test_main_app():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "[OPTIONS] COMMAND [ARGS]" in result.stdout


def test_validate_all_commands_have_names():
    assert app.registered_commands
    for command in app.registered_commands:
        assert command.name


def test_validate_all_groups_have_names():
    assert app.registered_groups
    for group in app.registered_groups:
        assert group.name


@requires_python_310
def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Python SDK: v" in result.stdout


@requires_python_310
def test_info_command_success(mock_query_infrahub_version, mock_query_infrahub_user):
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    for expected in ["Connection Status", "Python Version", "SDK Version", "Infrahub Version"]:
        assert expected in result.stdout, f"'{expected}' not found in info command output"


@requires_python_310
def test_info_command_failure():
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Connection Error" in result.stdout


@requires_python_310
def test_info_detail_command_success(mock_query_infrahub_version, mock_query_infrahub_user):
    result = runner.invoke(app, ["info", "--detail"])
    assert result.exit_code == 0
    for expected in [
        "Connection Status",
        "Version Information",
        "Client Info",
        "Infrahub Info",
        "Groups:",
    ]:
        assert expected in result.stdout, f"'{expected}' not found in detailed info command output"


@requires_python_310
def test_info_detail_command_failure():
    result = runner.invoke(app, ["info", "--detail"])
    assert result.exit_code == 0
    assert "Error Reason" in result.stdout
