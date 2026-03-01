from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl.marketplace import app

runner = CliRunner()

SCHEMA_YAML = """---
version: "1.0"
nodes:
  - name: Device
    namespace: Infra
"""


def test_download_schema_latest(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    result = runner.invoke(app, ["download", "acme/network-base", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded acme/network-base v1.2.0" in result.stdout
    written = tmp_path / "acme-network-base-1.2.0.yml"
    assert written.exists()
    assert written.read_text() == SCHEMA_YAML


def test_download_schema_specific_version(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/0.9.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["download", "acme/network-base", "-v", "0.9.0", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded acme/network-base v0.9.0" in result.stdout
    written = tmp_path / "acme-network-base-0.9.0.yml"
    assert written.exists()


def test_download_collection(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack/download",
        json={
            "collection": {
                "namespace": "acme",
                "name": "starter-pack",
                "schema_count": 2,
                "downloaded_count": 2,
                "skipped": [],
            },
            "schemas": [
                {
                    "namespace": "acme",
                    "name": "network-base",
                    "semver": "1.0.0",
                    "filename": "acme-network-base-1.0.0.yml",
                    "content": SCHEMA_YAML,
                },
                {
                    "namespace": "acme",
                    "name": "dcim",
                    "semver": "2.1.0",
                    "filename": "acme-dcim-2.1.0.yml",
                    "content": SCHEMA_YAML,
                },
            ],
        },
    )
    result = runner.invoke(app, ["download", "acme/starter-pack", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded acme/network-base v1.0.0" in result.stdout
    assert "Downloaded acme/dcim v2.1.0" in result.stdout
    assert "2/2 schemas downloaded" in result.stdout
    assert (tmp_path / "acme-network-base-1.0.0.yml").exists()
    assert (tmp_path / "acme-dcim-2.1.0.yml").exists()


def test_download_schema_404(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/nonexistent/download",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    result = runner.invoke(app, ["download", "acme/nonexistent", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "Schema not found" in result.stdout


def test_download_invalid_identifier(tmp_path: Path) -> None:
    result = runner.invoke(app, ["download", "invalid-no-slash", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "Invalid identifier" in result.stdout


def test_download_custom_marketplace_url(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/api/v1/schemas/acme/test/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.0.0"},
    )
    result = runner.invoke(
        app,
        ["download", "acme/test", "-o", str(tmp_path), "--marketplace-url", "http://localhost:8000"],
    )

    assert result.exit_code == 0
    assert "Downloaded acme/test v1.0.0" in result.stdout


def test_download_collection_with_skipped(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/mixed/download",
        json={
            "collection": {
                "namespace": "acme",
                "name": "mixed",
                "schema_count": 2,
                "downloaded_count": 1,
                "skipped": [
                    {"namespace": "acme", "name": "broken", "reason": "no published version"},
                ],
            },
            "schemas": [
                {
                    "namespace": "acme",
                    "name": "good",
                    "semver": "1.0.0",
                    "filename": "acme-good-1.0.0.yml",
                    "content": SCHEMA_YAML,
                },
            ],
        },
    )
    result = runner.invoke(app, ["download", "acme/mixed", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Skipped acme/broken" in result.stdout
    assert "1/2 schemas downloaded" in result.stdout
