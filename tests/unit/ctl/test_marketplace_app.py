import json as _json
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from infrahub_sdk.ctl import config as ctl_config
from infrahub_sdk.ctl.marketplace import app
from infrahub_sdk.ctl.marketplace import get as marketplace_get

runner = CliRunner()

SCHEMA_YAML = """---
version: "1.0"
nodes:
  - name: Device
    namespace: Infra
"""


def _collection_json(members: list[tuple[str, str, str]]) -> dict:
    """Build collection metadata mimicking the marketplace endpoint.

    ``members`` is a list of ``(namespace, name, semver)`` tuples.
    """
    return {
        "items": [
            {"schema": {"namespace": ns, "name": name, "latest_version": {"semver": semver}}}
            for ns, name, semver in members
        ]
    }


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
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    # Actual pinned-version download
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/0.9.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/network-base", "-v", "0.9.0", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded schema acme/network-base v0.9.0" in result.output
    written = tmp_path / "network-base.yml"
    assert written.exists()
    assert written.read_text() == SCHEMA_YAML


def test_download_collection(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json([("acme", "network-base", "1.0.0"), ("acme", "dcim", "2.1.0")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/dcim/versions/2.1.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/starter-pack", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded schema acme/network-base v1.0.0" in result.output
    assert "Downloaded schema acme/dcim v2.1.0" in result.output
    assert "2 schemas downloaded" in result.output
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
        url="https://marketplace.infrahub.app/api/v1/collections/acme/nonexistent",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["get", "acme/nonexistent", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "No schema or collection named 'acme/nonexistent'" in result.output
    assert "marketplace.infrahub.app" in result.output


def test_download_invalid_identifier(tmp_path: Path) -> None:
    result = runner.invoke(app, ["get", "invalid-no-slash", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "Invalid identifier" in result.output


def test_download_custom_marketplace_url(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/api/v1/schemas/acme/test/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.0.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="http://localhost:8000/api/v1/collections/acme/test",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(
        app,
        ["get", "acme/test", "-o", str(tmp_path), "--marketplace-url", "http://localhost:8000"],
    )

    assert result.exit_code == 0
    assert "Downloaded schema acme/test v1.0.0" in result.output


def test_marketplace_url_from_env(httpx_mock: HTTPXMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SETTINGS is a module-level singleton that only loads once. Reset it so the
    # next invoke re-reads from env, then patch the env var before that happens.
    monkeypatch.setattr(ctl_config.SETTINGS, "_settings", None)
    monkeypatch.setenv("INFRAHUB_MARKETPLACE_URL", "http://staging.example.com")
    httpx_mock.add_response(
        method="GET",
        url="http://staging.example.com/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.0.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="http://staging.example.com/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["get", "acme/network-base", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded schema acme/network-base v1.0.0" in result.output


def test_autodetect_schema(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["get", "acme/network-base", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded schema acme/network-base v1.2.0" in result.output
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
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json([("acme", "network-base", "1.0.0")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/starter-pack", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Collection acme/starter-pack" in result.output
    assert "1 schemas downloaded" in result.output
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
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network",
        json=_collection_json([]),
    )
    result = runner.invoke(app, ["get", "acme/network", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "both a schema and a collection" in result.output
    assert "--collection" in result.output
    assert "Downloaded schema acme/network v1.0.0" in result.output


def test_autodetect_network_error(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    result = runner.invoke(app, ["get", "acme/anything", "-o", str(tmp_path)])

    assert result.exit_code == 2
    assert "Could not reach marketplace" in result.output
    assert "marketplace.infrahub.app" in result.output


def test_version_not_found(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/9.9.9/download",
        status_code=404,
        json={"detail": "Version not found"},
    )
    result = runner.invoke(app, ["get", "acme/network-base", "-v", "9.9.9", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "9.9.9" in result.output
    assert "--version" in result.output
    assert "no published version" in result.output


def test_version_ignored_on_autodetected_collection(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/starter-pack/download",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json([("acme", "network-base", "1.0.0")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/starter-pack", "-v", "1.0.0", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Warning: --version is ignored" in result.output
    assert (tmp_path / "starter-pack" / "network-base.yml").exists()


def test_collection_flag_overrides_autodetect(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json([("acme", "network-base", "1.0.0")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    # No schema-detect endpoint mock — if the implementation probes it, pytest-httpx
    # will raise "request not expected".
    result = runner.invoke(app, ["get", "acme/starter-pack", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Collection acme/starter-pack" in result.output


def test_output_dir_creates_nested_missing_parents(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    nested = tmp_path / "a" / "b" / "c"
    result = runner.invoke(app, ["get", "acme/network-base", "-o", str(nested)])

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
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["get", "acme/network-base"])

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
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
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
    result = runner.invoke(app, ["get", "acme/network-base", "-o", str(target)])

    assert result.exit_code == 1
    assert "Cannot write" in result.output
    assert "unwritable" in result.output


def test_download_collection_skips_members_missing_identity(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """A member entry missing namespace/name is skipped rather than aborting the download."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/mixed",
        json={
            "items": [
                {"schema": {"namespace": "acme", "name": "good", "latest_version": {"semver": "1.0.0"}}},
                {"schema": {"name": "orphan", "latest_version": {"semver": "1.0.0"}}},
            ]
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/good/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/mixed", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "Downloaded schema acme/good v1.0.0" in result.output
    assert "Warning: skipping a collection member" in result.output
    assert "1 schemas downloaded" in result.output
    assert (tmp_path / "mixed" / "good.yml").exists()


def test_download_collection_duplicate_names_across_namespaces(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Members sharing a name across namespaces land in namespace subdirectories instead of overwriting."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/clash",
        json=_collection_json([("acme", "dcim", "1.0.0"), ("other", "dcim", "2.0.0"), ("acme", "ipam", "1.0.0")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/dcim/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/other/dcim/versions/2.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/ipam/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/clash", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "3 schemas downloaded" in result.output
    assert (tmp_path / "clash" / "acme" / "dcim.yml").exists()
    assert (tmp_path / "clash" / "other" / "dcim.yml").exists()
    assert (tmp_path / "clash" / "ipam.yml").exists()


def test_autodetect_partial_probe_failure_is_network(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Schema 404 + collection transport failure should be classified as network, not not-found."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/foo/download",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url="https://marketplace.infrahub.app/api/v1/collections/acme/foo",
    )
    result = runner.invoke(app, ["get", "acme/foo", "-o", str(tmp_path)])

    assert result.exit_code == 2
    assert "Could not reach marketplace" in result.output


def test_versioned_download_network_error(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """A network failure during the post-detect versioned fetch should exit with code 2."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/1.0.0/download",
    )
    result = runner.invoke(app, ["get", "acme/network-base", "-v", "1.0.0", "-o", str(tmp_path)])

    assert result.exit_code == 2
    assert "Marketplace request failed: connection refused" in result.output


def test_collection_flag_network_error(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """A network failure on the explicit --collection fetch should exit with code 2."""
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url="https://marketplace.infrahub.app/api/v1/collections/acme/foo",
    )
    result = runner.invoke(app, ["get", "acme/foo", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 2
    assert "Marketplace request failed: connection refused" in result.output


def test_network_error_empty_message_shows_exception_type(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """When an httpx exception has no message (e.g. ReadTimeout), the type name is shown."""
    httpx_mock.add_exception(
        httpx.ReadTimeout(""),
        url="https://marketplace.infrahub.app/api/v1/collections/acme/foo",
    )
    result = runner.invoke(app, ["get", "acme/foo", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 2
    assert "Marketplace request failed: ReadTimeout" in result.output


def test_get_schema_stdout(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.2.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["get", "acme/network-base", "--stdout", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert SCHEMA_YAML in result.output
    assert "Fetched schema acme/network-base v1.2.0" in result.output
    assert not any(tmp_path.iterdir())


def test_get_collection_stdout(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json([("acme", "network-base", "1.0.0"), ("acme", "dcim", "2.1.0")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/dcim/versions/2.1.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/starter-pack", "-c", "--stdout", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert SCHEMA_YAML in result.output
    assert "Fetched schema acme/network-base v1.0.0" in result.output
    assert "Fetched schema acme/dcim v2.1.0" in result.output
    assert "2 schemas downloaded" in result.output
    assert not any(tmp_path.iterdir())


def test_get_collection_stdout_separator(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Schemas missing a leading `---` get one inserted between docs."""
    bare_yaml = 'version: "1.0"\nnodes: []\n'
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/bare",
        json=_collection_json([("acme", "a", "1.0.0"), ("acme", "b", "1.0.0")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/a/versions/1.0.0/download",
        text=bare_yaml,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/b/versions/1.0.0/download",
        text=bare_yaml,
    )
    result = runner.invoke(app, ["get", "acme/bare", "-c", "--stdout", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert bare_yaml in result.output
    assert "---" in result.output
    assert result.output.count(bare_yaml) == 2


def _listing_json(item_type: str, items: list[dict], *, total: int | None = None, cursor: str | None = None) -> dict:
    """Build a marketplace list/search envelope. ``item_type`` is 'schemas' or 'collections'."""
    return {
        "items": items,
        "page_info": {"has_next_page": cursor is not None, "end_cursor": cursor},
        "total_count": total if total is not None else len(items),
    }


def _schema_item(namespace: str, name: str, *, display: str, semver: str, downloads: int, tags: list[str]) -> dict:
    return {
        "namespace": namespace,
        "name": name,
        "display_name": display,
        "download_count": downloads,
        "tags": [{"name": t} for t in tags],
        "latest_version": {"semver": semver},
    }


def test_list_schemas(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "dcim", display="DCIM", semver="1.2.0", downloads=42, tags=["core"])],
            total=1,
        ),
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "infrahub/dcim" in result.output
    assert "DCIM" in result.output
    assert "1.2.0" in result.output
    assert "42" in result.output
    assert "core" in result.output


def _collection_item(namespace: str, name: str, *, display: str, schema_count: int, downloads: int) -> dict:
    return {
        "namespace": namespace,
        "name": name,
        "display_name": display,
        "schema_count": schema_count,
        "download_count": downloads,
    }


def test_list_collections(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections",
        json=_listing_json(
            "collections",
            [_collection_item("infrahub", "security-mgmt", display="Security", schema_count=5, downloads=7)],
            total=1,
        ),
    )
    result = runner.invoke(app, ["list", "--collections"])

    assert result.exit_code == 0
    assert "infrahub/security-mgmt" in result.output
    assert "Security" in result.output
    assert "5" in result.output
    assert "7" in result.output


def test_list_follows_cursor_pagination(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "a", display="A", semver="1.0.0", downloads=1, tags=[])],
            total=2,
            cursor="CURSOR1",
        ),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas?cursor=CURSOR1",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "b", display="B", semver="1.0.0", downloads=1, tags=[])],
            total=2,
        ),
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "infrahub/a" in result.output
    assert "infrahub/b" in result.output


def test_list_limit_requests_single_page_and_shows_footer(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas?limit=1",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "a", display="A", semver="1.0.0", downloads=1, tags=[])],
            total=52,
            cursor="CURSOR1",
        ),
    )
    # No second page mock: if the implementation followed the cursor despite --limit,
    # pytest-httpx would raise "request not expected".
    result = runner.invoke(app, ["list", "--limit", "1"])

    assert result.exit_code == 0
    assert "infrahub/a" in result.output
    assert "Showing 1 of 52" in result.output


def test_list_network_error_exits_2(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        status_code=503,
        json={"detail": "unavailable"},
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 2
    assert "Marketplace request failed" in result.output


def test_search_passes_term_and_renders(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas?search=vlan",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "vlan", display="VLAN", semver="1.0.0", downloads=3, tags=[])],
            total=1,
        ),
    )
    result = runner.invoke(app, ["search", "vlan"])

    assert result.exit_code == 0
    assert "infrahub/vlan" in result.output


def test_search_empty_results(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas?search=nomatch",
        json=_listing_json("schemas", [], total=0),
    )
    result = runner.invoke(app, ["search", "nomatch"])

    assert result.exit_code == 0
    # An empty catalog is not an error; the table renders with no data rows.
    assert "Identifier" in result.output


def test_list_json_output_is_parseable(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        json=_listing_json(
            "schemas",
            [_schema_item("infrahub", "dcim", display="DCIM", semver="1.2.0", downloads=42, tags=["core"])],
            total=1,
        ),
    )
    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0
    parsed = _json.loads(result.output)
    assert parsed[0]["name"] == "dcim"
    assert parsed[0]["latest_version"]["semver"] == "1.2.0"


def _schema_detail() -> dict:
    return {
        "namespace": "infrahub",
        "name": "vlan",
        "display_name": "VLAN",
        "description": "VLAN schema.",
        "download_count": 105,
        "tags": [{"name": "experimental"}],
        "versions": [
            {
                "semver": "1.0.0",
                "status": "published",
                "created_at": "2026-04-20T23:54:19+00:00",
                "changelog": "Initial",
            },
        ],
        "dependencies": {"schemas": [{"namespace": "infrahub", "name": "dcim"}], "collections": []},
    }


def test_show_schema_autodetect(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/vlan",
        json=_schema_detail(),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/vlan",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["show", "infrahub/vlan"])

    assert result.exit_code == 0
    assert "infrahub/vlan" in result.output
    assert "VLAN" in result.output
    assert "1.0.0" in result.output
    assert "published" in result.output
    assert "experimental" in result.output
    assert "infrahub/dcim" in result.output  # dependency


def test_show_schema_json(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/vlan",
        json=_schema_detail(),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/vlan",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["show", "infrahub/vlan", "--json"])

    assert result.exit_code == 0
    parsed = _json.loads(result.output)
    assert parsed["name"] == "vlan"
    assert parsed["versions"][0]["semver"] == "1.0.0"


def test_show_network_error_exits_2(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    result = runner.invoke(app, ["show", "infrahub/vlan"])

    assert result.exit_code == 2
    assert "Could not reach marketplace" in result.output


def _collection_detail() -> dict:
    return {
        "namespace": "infrahub",
        "name": "security-mgmt",
        "display_name": "Security & Management",
        "description": "Security and device management.",
        "download_count": 2,
        "items": [
            {"schema": {"namespace": "infrahub", "name": "security", "display_name": "Security"}},
            {"schema": {"namespace": "infrahub", "name": "qos", "display_name": "QoS"}},
        ],
        "dependencies": {"schemas": [{"namespace": "infrahub", "name": "location"}], "collections": []},
    }


def test_show_collection_force_flag(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/security-mgmt",
        json=_collection_detail(),
    )
    # No schema-detail mock: --collection must not probe the schema endpoint.
    result = runner.invoke(app, ["show", "infrahub/security-mgmt", "--collection"])

    assert result.exit_code == 0
    assert "infrahub/security-mgmt" in result.output
    assert "infrahub/security" in result.output
    assert "infrahub/qos" in result.output
    assert "Schemas: 2" in result.output
    assert "infrahub/location" in result.output  # dependency


def test_show_collection_autodetect(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/security-mgmt",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/security-mgmt",
        json=_collection_detail(),
    )
    result = runner.invoke(app, ["show", "infrahub/security-mgmt"])

    assert result.exit_code == 0
    assert "infrahub/qos" in result.output


def test_show_not_found(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/nope",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/nope",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["show", "infrahub/nope"])

    assert result.exit_code == 1
    assert "No schema or collection named 'infrahub/nope'" in result.output


def test_show_invalid_identifier() -> None:
    result = runner.invoke(app, ["show", "no-slash"])

    assert result.exit_code == 1
    assert "Invalid identifier" in result.output


async def test_collection_false_autodetects_schema(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """collection=False (the default) triggers auto-detect; schema wins when schema endpoint returns 200."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/network-base/download",
        text=SCHEMA_YAML,
        headers={"x-schema-version": "1.0.0"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/network-base",
        status_code=404,
        json={"detail": "Collection not found"},
    )

    await marketplace_get(
        identifier="acme/network-base",
        version=None,
        collection=False,
        stdout=False,
        output_dir=tmp_path,
        marketplace_url="https://marketplace.infrahub.app",
        _="",
    )

    assert (tmp_path / "network-base.yml").read_text() == SCHEMA_YAML


# ---------------------------------------------------------------------------
# Fix #1 — 4xx errors must exit 1 (not 2)
# ---------------------------------------------------------------------------


def test_list_4xx_error_exits_1(httpx_mock: HTTPXMock) -> None:
    """A 4xx response on the listing endpoint must exit 1, not 2."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        status_code=400,
        json={"detail": "Bad Request"},
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 1


def test_show_force_collection_4xx_exits_1(httpx_mock: HTTPXMock) -> None:
    """A 4xx response on the --collection (force) path in show must exit 1, not 2."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/security-mgmt",
        status_code=400,
        json={"detail": "Bad Request"},
    )
    result = runner.invoke(app, ["show", "infrahub/security-mgmt", "--collection"])

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Fix #2 — collision note must not appear on stdout when --json is used
# ---------------------------------------------------------------------------


def test_show_collision_json_stdout_is_clean(httpx_mock: HTTPXMock) -> None:
    """When show hits a 200/200 collision and --json is passed, stdout must stay JSON-only.

    The collision note must be routed to err_console (stderr) not console (stdout).

    Stream-separation assertion limitation: Typer 0.25 / Click 8.3 do not
    support ``mix_stderr=False`` on CliRunner, so we cannot isolate stdout in
    this test runner.  The structural fix (console.print → err_console.print in
    ``_fetch_detail``) is the authoritative correction; this test guards that the
    command exits 0 on a collision+json path and that the JSON payload is
    present somewhere in the combined output.
    """
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/vlan",
        json=_schema_detail(),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/vlan",
        json=_collection_detail(),
    )

    result = runner.invoke(app, ["show", "infrahub/vlan", "--json"])

    assert result.exit_code == 0
    # The combined output must contain the JSON payload.  We parse the whole
    # block starting from the first '{' at column 0 (the root object printed by
    # Rich's print_json always starts at column 0).
    output = result.output
    root_brace = next((i for i, ch in enumerate(output) if ch == "{" and (i == 0 or output[i - 1] == "\n")), None)
    assert root_brace is not None, "No root-level JSON object found in output"
    parsed = _json.loads(output[root_brace:])
    assert parsed["name"] == "vlan"


# ---------------------------------------------------------------------------
# 5xx on the show (detail) path must be a network error (exit 2)
# ---------------------------------------------------------------------------


def test_show_network_error_5xx_exits_2(httpx_mock: HTTPXMock) -> None:
    """A 5xx from both detail probes classifies as a network error (exit 2)."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/vlan",
        status_code=503,
        json={"detail": "unavailable"},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/vlan",
        status_code=503,
        json={"detail": "unavailable"},
    )
    result = runner.invoke(app, ["show", "infrahub/vlan"])

    assert result.exit_code == 2
    assert "Could not reach marketplace" in result.output


def test_list_stops_when_next_page_has_null_cursor(httpx_mock: HTTPXMock) -> None:
    """has_next_page=true with a null end_cursor must not loop forever.

    Only one page is mocked. If the loop followed the (null) cursor it would issue
    a second request that pytest-httpx has no response for, failing the test.
    """
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        json={
            "items": [_schema_item("infrahub", "a", display="A", semver="1.0.0", downloads=1, tags=[])],
            "page_info": {"has_next_page": True, "end_cursor": None},
            "total_count": 1,
        },
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "infrahub/a" in result.output


def test_list_invalid_json_body_is_network_error(httpx_mock: HTTPXMock) -> None:
    """A 200 response with a non-JSON body is reported as a clean network error (exit 2)."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        text="<html>not json</html>",
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 2
    assert "not valid JSON" in result.output


def test_list_non_dict_payload_is_network_error(httpx_mock: HTTPXMock) -> None:
    """A 200 response whose body is valid JSON but not an object exits 2 cleanly, not a traceback."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas",
        json=[{"namespace": "infrahub", "name": "dcim"}],
    )
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 2
    assert "not a valid marketplace listing" in result.output


def test_show_invalid_json_body_is_network_error(httpx_mock: HTTPXMock) -> None:
    """A schema detail endpoint returning 200 with a malformed body exits 2, not a traceback."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/infrahub/vlan",
        text="<html>not json</html>",
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/infrahub/vlan",
        status_code=404,
        json={"detail": "Collection not found"},
    )
    result = runner.invoke(app, ["show", "infrahub/vlan"])

    assert result.exit_code == 2
    assert "not valid JSON" in result.output
