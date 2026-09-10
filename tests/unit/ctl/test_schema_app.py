# ruff: noqa: PLC2701
from dataclasses import dataclass

import pytest
import typer
import yaml
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl.schema import _display_schema_warnings, app, validate_schema_content_and_exit
from infrahub_sdk.ctl.utils import get_fixtures_dir
from infrahub_sdk.schema import SchemaWarning, SchemaWarningKind, SchemaWarningType
from tests.helpers.cli import remove_ansi_color
from tests.helpers.schema_load_errors import INVALID_SCHEMA, VALID_SCHEMA, capture_console, make_console, schema_files

runner = CliRunner()


def test_schema_load_empty(httpx_mock: HTTPXMock) -> None:
    fixture_file = get_fixtures_dir() / "models" / "empty.json"
    result = runner.invoke(app=app, args=["load", str(fixture_file)])

    assert result.exit_code == 1
    assert "Invalid YAML/JSON file" in result.stdout


def test_schema_load_one_valid(httpx_mock: HTTPXMock) -> None:
    fixture_file = get_fixtures_dir() / "models" / "valid_model_01.json"

    httpx_mock.add_response(
        method="POST",
        url="http://mock/api/schema/load?branch=main",
        status_code=200,
        json={
            "hash": "497c17fbe915062c8c5a698be62130e4",
            "previous_hash": "d3f7f4e7161f0ae6538a01d5a42dc661",
            "diff": {
                "added": {"InfraDevice": {"added": {}, "changed": {}, "removed": {}}},
                "changed": {},
                "removed": {},
            },
            "schema_updated": True,
        },
    )
    result = runner.invoke(app=app, args=["load", str(fixture_file)])

    assert result.exit_code == 0
    assert f"schema '{fixture_file}' loaded successfully" in remove_ansi_color(result.stdout.replace("\n", ""))

    content = httpx_mock.get_requests()[0].content.decode("utf8")
    content_json = yaml.safe_load(content)
    fixture_file_content = yaml.safe_load(
        fixture_file.read_text(encoding="utf-8"),
    )
    assert content_json == {"schemas": [fixture_file_content]}


def test_schema_load_multiple(httpx_mock: HTTPXMock) -> None:
    fixture_file1 = get_fixtures_dir() / "models" / "valid_schemas" / "contract.yml"
    fixture_file2 = get_fixtures_dir() / "models" / "valid_schemas" / "rack.yml"

    httpx_mock.add_response(
        method="POST",
        url="http://mock/api/schema/load?branch=main",
        status_code=200,
        json={
            "hash": "497c17fbe915062c8c5a698be62130e4",
            "previous_hash": "d3f7f4e7161f0ae6538a01d5a42dc661",
            "diff": {
                "added": {"InfraDevice": {"added": {}, "changed": {}, "removed": {}}},
                "changed": {},
                "removed": {},
            },
            "schema_updated": True,
        },
    )
    result = runner.invoke(app=app, args=["load", str(fixture_file1), str(fixture_file2)])

    assert result.exit_code == 0
    clean_output = remove_ansi_color(result.stdout.replace("\n", ""))
    assert f"schema '{fixture_file1}' loaded successfully" in clean_output
    assert f"schema '{fixture_file2}' loaded successfully" in clean_output

    content = httpx_mock.get_requests()[0].content.decode("utf8")
    content_json = yaml.safe_load(content)
    fixture_file1_content = yaml.safe_load(fixture_file1.read_text(encoding="utf-8"))
    fixture_file2_content = yaml.safe_load(fixture_file2.read_text(encoding="utf-8"))
    assert content_json == {"schemas": [fixture_file1_content, fixture_file2_content]}


def test_schema_load_notvalid_namespace() -> None:
    """An invalid namespace is now rejected client-side by the write contract.

    The SDK write models mirror the server's field constraints, so ``infrahubctl load``
    catches an invalid namespace during local validation and exits before sending the
    payload to the server.
    """
    fixture_file = get_fixtures_dir() / "models" / "non_valid_namespace.json"

    result = runner.invoke(app=app, args=["load", str(fixture_file)])

    assert result.exit_code == 1

    clean_output = remove_ansi_color(result.stdout.replace("\n", ""))
    assert "Schema not valid" in clean_output
    assert "nodes[0].namespace" in clean_output
    assert "String should match pattern" in clean_output
    assert "received: 'OuT'" in clean_output


def test_load_valid_generic_schema(httpx_mock: HTTPXMock) -> None:
    """A test which ensures that a generic schema is correctly loaded when loaded from infrahubctl command."""
    # Arrange
    fixture_file = get_fixtures_dir() / "models" / "valid_generic_schema.json"

    httpx_mock.add_response(
        method="POST",
        url="http://mock/api/schema/load?branch=main",
        status_code=200,
        json={
            "hash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            "previous_hash": "d3f7f4e7161f0ae6538a01d5a42dc661",
            "diff": {
                "added": {
                    "TestingAnimal": {"added": {}, "changed": {}, "removed": {}},
                    "DogDog": {"added": {}, "changed": {}, "removed": {}},
                },
                "changed": {},
                "removed": {},
            },
            "schema_updated": True,
        },
    )

    # Act
    result = runner.invoke(app=app, args=["load", str(fixture_file)])

    # Assert
    assert result.exit_code == 0
    assert f"schema '{fixture_file}' loaded successfully" in remove_ansi_color(result.stdout.replace("\n", ""))

    content = httpx_mock.get_requests()[0].content.decode("utf8")
    content_json = yaml.safe_load(content)
    fixture_file_content = yaml.safe_load(
        fixture_file.read_text(encoding="utf-8"),
    )
    assert content_json == {"schemas": [fixture_file_content]}

    # Verify restricted_namespaces is present in the payload sent to the API
    sent_generics = content_json["schemas"][0]["generics"]
    assert len(sent_generics) == 1
    assert sent_generics[0]["restricted_namespaces"] == ["Dog"]


# ---------------------------------------------------------------------------------------------------------------------


def test_validate_schema_content_valid_schemas_print_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    output = capture_console(monkeypatch)
    validate_schema_content_and_exit(schemas=schema_files(VALID_SCHEMA, VALID_SCHEMA))
    assert not output.getvalue()


def test_validate_schema_content_no_files(monkeypatch: pytest.MonkeyPatch) -> None:
    output = capture_console(monkeypatch)
    validate_schema_content_and_exit(schemas=[])
    assert not output.getvalue()


def test_validate_schema_content_reports_every_error_of_every_invalid_file_then_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = capture_console(monkeypatch)
    markup = {"version": "1.0", "bogus": "[red]x[/red]", "nodes": []}

    with pytest.raises(typer.Exit) as exc:
        validate_schema_content_and_exit(schemas=schema_files(VALID_SCHEMA, INVALID_SCHEMA, markup))

    assert exc.value.exit_code == 1
    assert output.getvalue() == (
        "Schema not valid, found '2' error(s) in schema-1.yml\n"
        "  nodes[0].namespace: String should match pattern '^[A-Z][a-z0-9]+$' (received: 'infra')\n"
        "  nodes[0].attributes[0].Text.name: String should have at least 3 characters (received: 'n')\n"
        "Schema not valid, found '1' error(s) in schema-2.yml\n"
        "  bogus: Unknown field, it is not part of the schema (received: '[red]x[/red]')\n"
    )


@dataclass
class WarningCase:
    name: str
    warning: SchemaWarning
    expected: str


WARNING_CASES = [
    WarningCase(
        name="no-kind",
        warning=SchemaWarning(type=SchemaWarningType.DEPRECATION, message="gone soon"),
        expected=" deprecation: gone soon\n",
    ),
    WarningCase(
        name="one-kind",
        warning=SchemaWarning(
            type=SchemaWarningType.DEPRECATION, message="gone soon", kinds=[SchemaWarningKind(kind="InfraDevice")]
        ),
        expected=" deprecation: gone soon [InfraDevice]\n",
    ),
    WarningCase(
        name="kinds-with-field",
        warning=SchemaWarning(
            type=SchemaWarningType.DEPRECATION,
            message="gone soon",
            kinds=[SchemaWarningKind(kind="InfraDevice", field="serial"), SchemaWarningKind(kind="InfraSite")],
        ),
        expected=" deprecation: gone soon [InfraDevice.serial, InfraSite]\n",
    ),
    WarningCase(
        name="markup-in-message-is-escaped",
        warning=SchemaWarning(type=SchemaWarningType.DEPRECATION, message="[bold]x[/bold] stays literal"),
        expected=" deprecation: [bold]x[/bold] stays literal\n",
    ),
]


@pytest.mark.parametrize("case", [pytest.param(tc, id=tc.name) for tc in WARNING_CASES])
def test_display_schema_warnings(case: WarningCase) -> None:
    console, output = make_console()
    _display_schema_warnings(console=console, warnings=[case.warning])
    assert output.getvalue() == case.expected


def test_display_schema_warnings_none() -> None:
    console, output = make_console()
    _display_schema_warnings(console=console, warnings=[])
    assert not output.getvalue()
