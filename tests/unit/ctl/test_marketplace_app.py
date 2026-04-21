from pathlib import Path

import httpx
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
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["download", "acme/network-base", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded schema acme/network-base v1.2.0" in result.stdout
    written = tmp_path / "network-base.yml"
    assert written.exists()
    assert written.read_text() == SCHEMA_YAML


def test_download_schema_specific_version(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    # Auto-detect probes
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    # Actual pinned-version download
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/0.9.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["download", "acme/network-base", "-v", "0.9.0", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded schema acme/network-base v0.9.0" in result.stdout
    written = tmp_path / "network-base.yml"
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
    assert (tmp_path / "starter-pack" / "network-base.yml").exists()
    assert (tmp_path / "starter-pack" / "dcim.yml").exists()


def test_download_not_found(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/nonexistent/download",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/nonexistent/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["download", "acme/nonexistent", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "acme/nonexistent" in result.stdout
    assert "marketplace.infrahub.app" in result.stdout


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
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/api/v1/collections/acme/test/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(
        app,
        ["download", "acme/test", "-o", str(tmp_path), "--marketplace-url", "http://localhost:8000"],
    )

    assert result.exit_code == 0
    assert "Downloaded schema acme/test v1.0.0" in result.stdout


def test_autodetect_schema(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["download", "acme/network-base", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded schema acme/network-base v1.2.0" in result.stdout
    assert (tmp_path / "network-base.yml").exists()


def test_autodetect_collection(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/starter-pack/download",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack/download",
        json={
            "collection": {
                "namespace": "acme",
                "name": "starter-pack",
                "schema_count": 1,
                "downloaded_count": 1,
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
            ],
        },
    )
    result = runner.invoke(app, ["download", "acme/starter-pack", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Collection acme/starter-pack" in result.stdout
    assert "1/1 schemas downloaded" in result.stdout
    assert (tmp_path / "starter-pack" / "network-base.yml").exists()


def test_autodetect_collision_schema_wins(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.0.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network/download",
        json={
            "collection": {
                "namespace": "acme",
                "name": "network",
                "schema_count": 0,
                "downloaded_count": 0,
                "skipped": [],
            },
            "schemas": [],
        },
    )
    result = runner.invoke(app, ["download", "acme/network", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "both a schema and a collection" in result.stdout
    assert "--collection" in result.stdout
    assert "Downloaded schema acme/network v1.0.0" in result.stdout


def test_autodetect_network_error(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    result = runner.invoke(app, ["download", "acme/anything", "-o", str(tmp_path)])

    assert result.exit_code == 2
    assert "Could not reach marketplace" in result.stdout
    assert "marketplace.infrahub.app" in result.stdout


def test_version_not_found(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/9.9.9/download",
        status_code=404,
        json={"detail": "Version not found"},
    )
    result = runner.invoke(app, ["download", "acme/network-base", "-v", "9.9.9", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "9.9.9" in result.stdout
    assert "--version" in result.stdout
    assert "no published version" in result.stdout


def test_version_ignored_on_autodetected_collection(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/starter-pack/download",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack/download",
        json={
            "collection": {
                "namespace": "acme",
                "name": "starter-pack",
                "schema_count": 1,
                "downloaded_count": 1,
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
            ],
        },
    )
    result = runner.invoke(app, ["download", "acme/starter-pack", "-v", "1.0.0", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Warning: --version is ignored" in result.stdout
    assert (tmp_path / "starter-pack" / "network-base.yml").exists()


def test_collection_flag_overrides_autodetect(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack/download",
        json={
            "collection": {
                "namespace": "acme",
                "name": "starter-pack",
                "schema_count": 1,
                "downloaded_count": 1,
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
            ],
        },
    )
    # No schema endpoint mock — if the implementation probes it, pytest-httpx
    # will raise "request not expected".
    result = runner.invoke(app, ["download", "acme/starter-pack", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Collection acme/starter-pack" in result.stdout


def test_output_dir_creates_nested_missing_parents(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    nested = tmp_path / "a" / "b" / "c"
    result = runner.invoke(app, ["download", "acme/network-base", "-o", str(nested)])

    assert result.exit_code == 0
    assert (nested / "network-base.yml").exists()


def test_output_dir_default_is_schemas(httpx_mock: HTTPXMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["download", "acme/network-base"])

    assert result.exit_code == 0
    assert (tmp_path / "schemas" / "network-base.yml").exists()


def test_output_dir_permission_error(httpx_mock: HTTPXMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base/download",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    original_mkdir = Path.mkdir

    def raising_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        if str(self).endswith("/unwritable"):
            raise PermissionError(f"[Errno 13] Permission denied: {self}")
        original_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", raising_mkdir)

    target = tmp_path / "unwritable"
    result = runner.invoke(app, ["download", "acme/network-base", "-o", str(target)])

    assert result.exit_code == 1
    assert "Cannot write" in result.stdout
    assert "unwritable" in result.stdout


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
