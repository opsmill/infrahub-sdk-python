from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml
from typer.testing import CliRunner

from infrahub_sdk.ctl.schema import app
from tests.helpers.cli import remove_ansi_color

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_httpx import HTTPXMock

runner = CliRunner()

DEVICE: dict[str, Any] = {"name": "Device", "namespace": "Network", "attributes": [{"name": "name", "kind": "Text"}]}
INTERFACE: dict[str, Any] = {
    "name": "Interface",
    "namespace": "Network",
    "attributes": [{"name": "name", "kind": "Text"}],
}
RACK: dict[str, Any] = {"name": "Rack", "namespace": "Dcim", "attributes": [{"name": "name", "kind": "Text"}]}
EXPORTED_SCHEMA: dict[str, Any] = {
    "version": "1.0",
    "infrahub_version": "1.13.0",
    "generics": [INTERFACE],
    "nodes": [RACK, DEVICE],
}


def _read_yaml(path: Path) -> dict[str, Any]:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(content, dict)
    return content


def test_export_writes_one_file_per_namespace(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET", url="http://mock/api/schema/export?branch=main&mode=brief", json=EXPORTED_SCHEMA
    )

    result = runner.invoke(app=app, args=["export", "--directory", str(tmp_path)])

    assert result.exit_code == 0, result.stdout
    assert sorted(path.name for path in tmp_path.iterdir()) == ["dcim.yml", "network.yml"]
    assert _read_yaml(tmp_path / "network.yml") == {
        "version": "1.0",
        "infrahub_version": "1.13.0",
        "generics": [INTERFACE],
        "nodes": [DEVICE],
    }
    assert _read_yaml(tmp_path / "dcim.yml") == {"version": "1.0", "infrahub_version": "1.13.0", "nodes": [RACK]}


def test_export_single_file_in_full_mode(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=main&mode=full&namespaces=Network&namespaces=Dcim",
        json=EXPORTED_SCHEMA,
    )

    result = runner.invoke(
        app=app,
        args=[
            "export",
            "--directory",
            str(tmp_path),
            "--single-file",
            "--mode",
            "full",
            "--namespaces",
            "Network",
            "--namespaces",
            "Dcim",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert [path.name for path in tmp_path.iterdir()] == ["schema.yml"]
    assert _read_yaml(tmp_path / "schema.yml") == EXPORTED_SCHEMA


def test_export_of_an_empty_schema_writes_no_file(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=main&mode=brief",
        json={"version": "1.0", "infrahub_version": "1.13.0", "generics": [], "nodes": []},
    )

    result = runner.invoke(app=app, args=["export", "--directory", str(tmp_path / "out")])

    assert result.exit_code == 0, result.stdout
    assert "No user-defined schema found to export." in result.stdout
    assert not (tmp_path / "out").exists()


def test_export_against_a_server_without_the_endpoint(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema/export?branch=main&mode=brief",
        status_code=422,
        json={"data": None, "errors": [{"message": "Unable to find the schema export in the database."}]},
    )

    result = runner.invoke(app=app, args=["export", "--directory", str(tmp_path)])

    assert result.exit_code == 1
    output = remove_ansi_color(result.stdout)
    assert output.strip() == "Schema export requires Infrahub 1.13.0 or later."
    assert "Traceback" not in output
