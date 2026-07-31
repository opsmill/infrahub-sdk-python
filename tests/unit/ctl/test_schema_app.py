import yaml
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl.schema import app
from infrahub_sdk.ctl.utils import get_fixtures_dir
from tests.helpers.cli import remove_ansi_color

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
