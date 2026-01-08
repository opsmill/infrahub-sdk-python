import pytest
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl.cli import app

runner = CliRunner()

pytestmark = pytest.mark.httpx_mock(can_send_already_matched_responses=True)


def test_main_app() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "[OPTIONS] COMMAND [ARGS]" in result.stdout


def test_validate_all_commands_have_names() -> None:
    assert app.registered_commands
    for command in app.registered_commands:
        assert command.name


def test_validate_all_groups_have_names() -> None:
    assert app.registered_groups
    for group in app.registered_groups:
        assert group.name


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Python SDK: v" in result.stdout


def test_info_command_success(mock_query_infrahub_version: HTTPXMock, mock_query_infrahub_user: HTTPXMock) -> None:
    result = runner.invoke(app, ["info"], env={"INFRAHUB_API_TOKEN": "foo"})
    assert result.exit_code == 0
    for expected in ["Connection Status", "Python Version", "SDK Version", "Infrahub Version"]:
        assert expected in result.stdout, f"'{expected}' not found in info command output"


def test_info_command_failure() -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Connection Error" in result.stdout


def test_info_detail_command_success(
    mock_query_infrahub_version: HTTPXMock, mock_query_infrahub_user: HTTPXMock
) -> None:
    result = runner.invoke(app, ["info", "--detail"], env={"INFRAHUB_API_TOKEN": "foo"})
    assert result.exit_code == 0
    for expected in ["Connection Status", "Version Information", "Client Info", "Infrahub Info", "Groups:"]:
        assert expected in result.stdout, f"'{expected}' not found in detailed info command output"


def test_anonymous_info_detail_command_success(mock_query_infrahub_version: HTTPXMock) -> None:
    result = runner.invoke(app, ["info", "--detail"])
    assert result.exit_code == 0
    for expected in ["Connection Status", "Version Information", "Client Info", "Infrahub Info", "anonymous"]:
        assert expected in result.stdout, f"'{expected}' not found in detailed info command output"


def test_info_detail_command_failure() -> None:
    result = runner.invoke(app, ["info", "--detail"])
    assert result.exit_code == 0
    assert "Error Reason" in result.stdout
