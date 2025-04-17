from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl.menu import app
from infrahub_sdk.ctl.utils import get_fixtures_dir
from tests.helpers.cli import remove_ansi_color

runner = CliRunner()


def test_menu_validate_bad_yaml() -> None:
    fixture_file = get_fixtures_dir() / "menus" / "invalid_yaml.yml"
    result = runner.invoke(app=app, args=["load", str(fixture_file)])

    assert result.exit_code == 1
    assert "Invalid YAML/JSON file" in result.stdout


def test_menu_validate_valid(mock_schema_query_05: HTTPXMock) -> None:
    fixture_file = get_fixtures_dir() / "menus" / "valid_menu.yml"

    result = runner.invoke(app=app, args=["validate", str(fixture_file)])

    assert result.exit_code == 0
    assert f"File '{fixture_file}' is Valid!" in remove_ansi_color(result.stdout.replace("\n", ""))


def test_menu_validate_invalid(mock_schema_query_05: HTTPXMock) -> None:
    fixture_file = get_fixtures_dir() / "menus" / "invalid_menu.yml"

    result = runner.invoke(app=app, args=["validate", str(fixture_file)])

    assert result.exit_code == 1
    assert f"File '{fixture_file}' is not valid! 1.namespace: namespace is mandatory" in remove_ansi_color(
        result.stdout.replace("\n", "")
    )
