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


def _collection_json(members: list[tuple[str, str, str]], dependencies: dict | None = None) -> dict:
    """Build collection metadata mimicking the marketplace endpoint.

    ``members`` is a list of ``(namespace, name, semver)`` tuples. ``dependencies`` is the
    optional derived-dependency object the detail endpoint returns.
    """
    payload: dict = {
        "items": [
            {"schema": {"namespace": ns, "name": name, "latest_version": {"semver": semver}}}
            for ns, name, semver in members
        ]
    }
    if dependencies is not None:
        payload["dependencies"] = dependencies
    return payload


def _deps(
    *,
    schemas: list[tuple[str, str]] | None = None,
    collections: list[tuple[str, str]] | None = None,
    unresolved: list[str] | None = None,
) -> dict:
    """Build a collection ``dependencies`` object (prerequisite collections + standalone schemas)."""
    return {
        "schemas": [{"id": f"s-{ns}-{nm}", "namespace": ns, "name": nm} for ns, nm in (schemas or [])],
        "collections": [{"id": f"c-{ns}-{nm}", "namespace": ns, "name": nm} for ns, nm in (collections or [])],
        "unresolved_kinds": unresolved or [],
        "hidden_count": 0,
    }


def _resolved_dep(namespace: str, name: str, kind: str | None = None) -> dict:
    return {
        "referenced_kind": kind or f"{namespace.capitalize()}{name.capitalize()}",
        "resolved_schema": {"id": f"s-{namespace}-{name}", "namespace": namespace, "name": name},
        "is_resolved": True,
        "multi_resolved": False,
        "hidden_due_to_visibility": False,
    }


def _unresolved_dep(kind: str, *, hidden: bool = False) -> dict:
    return {
        "referenced_kind": kind,
        "resolved_schema": None,
        "is_resolved": False,
        "multi_resolved": False,
        "hidden_due_to_visibility": hidden,
    }


def _schema_detail(namespace: str, name: str, *, semver: str = "1.0.0", deps: list[dict] | None = None) -> dict:
    """Build a schema-detail response mimicking GET /api/v1/schemas/{ns}/{name}."""
    version_id = f"v-{namespace}-{name}"
    return {
        "namespace": namespace,
        "name": name,
        "latest_version": {"id": version_id, "semver": semver},
        "versions": [{"id": version_id, "semver": semver, "dependencies": deps or []}],
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
        dependencies=False,
        stdout=False,
        output_dir=tmp_path,
        marketplace_url="https://marketplace.infrahub.app",
        _="",
    )

    assert (tmp_path / "network-base.yml").read_text() == SCHEMA_YAML


def test_dependencies_groups_prerequisite_collections_and_standalone(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """C1: members, prerequisite collections, and transitive standalone schemas land in the right dirs."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json(
            [("acme", "app", "1.0.0")],
            _deps(collections=[("acme", "base")], schemas=[("acme", "extra")]),
        ),
    )
    # Prerequisite collection → its own directory.
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/base",
        json=_collection_json([("acme", "dcim", "1.0.0"), ("acme", "ipam", "2.0.0")]),
    )
    # Standalone schema walk: extra → more (transitive), to the output root.
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/extra",
        json=_schema_detail("acme", "extra", deps=[_resolved_dep("acme", "more")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/more",
        json=_schema_detail("acme", "more", deps=[]),
    )
    for url in (
        "schemas/acme/app/versions/1.0.0/download",
        "schemas/acme/dcim/versions/1.0.0/download",
        "schemas/acme/ipam/versions/2.0.0/download",
        "schemas/acme/extra/download",
        "schemas/acme/more/download",
    ):
        httpx_mock.add_response(method="GET", url=f"https://marketplace.infrahub.app/api/v1/{url}", text=SCHEMA_YAML)
    result = runner.invoke(app, ["get", "acme/starter-pack", "-c", "--dependencies", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "5 schemas downloaded" in result.output
    assert "4 dependencies resolved" in result.output
    assert "Prerequisite collections: acme/base" in result.output
    # Requested collection members in its own dir.
    assert (tmp_path / "starter-pack" / "app.yml").exists()
    # Prerequisite collection members in their collection's dir.
    assert (tmp_path / "base" / "dcim.yml").exists()
    assert (tmp_path / "base" / "ipam.yml").exists()
    # Standalone dependency schemas at the output root.
    assert (tmp_path / "extra.yml").exists()
    assert (tmp_path / "more.yml").exists()


def test_dependencies_not_requested_skips_resolution(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """C2: without --dependencies, declared dependencies are ignored (backward compatible)."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json([("acme", "app", "1.0.0")], _deps(collections=[("acme", "base")])),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/app/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    # No /collections/acme/base mock — pytest-httpx fails if dependency resolution runs.
    result = runner.invoke(app, ["get", "acme/starter-pack", "-c", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "1 schemas downloaded" in result.output
    assert "dependencies resolved" not in result.output
    assert (tmp_path / "starter-pack" / "app.yml").exists()


def test_dependencies_collection_cycle_safe(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """A collection cycle A→B→A resolves each collection once."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/a",
        json=_collection_json([("acme", "sa", "1.0.0")], _deps(collections=[("acme", "b")])),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/b",
        json=_collection_json([("acme", "sb", "1.0.0")], _deps(collections=[("acme", "a")])),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/sa/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/sb/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/a", "-c", "--dependencies", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "2 schemas downloaded" in result.output
    assert "1 dependency resolved" in result.output
    assert "Prerequisite collections: acme/b" in result.output
    assert (tmp_path / "a" / "sa.yml").exists()
    assert (tmp_path / "b" / "sb.yml").exists()


def test_dependencies_member_also_standalone_downloaded_once(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """A schema that is both a member and a standalone dependency is written once (as a member)."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/pair",
        json=_collection_json([("acme", "a", "1.0.0"), ("acme", "b", "2.0.0")], _deps(schemas=[("acme", "b")])),
    )
    # The standalone walk reads b's dependencies but b is already a member, so it is not re-downloaded.
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/b",
        json=_schema_detail("acme", "b", deps=[]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/a/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/b/versions/2.0.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/pair", "-c", "--dependencies", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "2 schemas downloaded" in result.output
    assert "0 dependencies resolved" in result.output
    assert (tmp_path / "pair" / "b.yml").exists()


def test_dependencies_stdout_streams_all_documents(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """C4: --dependencies --stdout streams members, prerequisite-collection, and standalone schemas; no files."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json(
            [("acme", "a", "1.0.0")],
            _deps(collections=[("acme", "base")], schemas=[("acme", "ext")]),
        ),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/base",
        json=_collection_json([("acme", "bb", "1.0.0")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/ext",
        json=_schema_detail("acme", "ext", deps=[]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/a/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/bb/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/ext/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/starter-pack", "-c", "--dependencies", "--stdout", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert result.output.count(SCHEMA_YAML) == 3
    assert "Fetched schema acme/a v1.0.0" in result.output
    assert "Fetched schema acme/bb v1.0.0" in result.output
    assert "Fetched schema acme/ext" in result.output
    assert "2 dependencies resolved" in result.output
    assert not any(tmp_path.iterdir())


def test_dependencies_unresolved_kinds_reported(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """C6: referenced kinds the marketplace cannot resolve are listed as unresolved dependencies."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/starter-pack",
        json=_collection_json([("acme", "app", "1.0.0")], _deps(unresolved=["BuiltinTag", "BuiltinIPHost"])),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/app/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    result = runner.invoke(app, ["get", "acme/starter-pack", "-c", "--dependencies", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "0 dependencies resolved" in result.output
    assert "Unresolved dependencies" in result.output
    assert "BuiltinTag" in result.output
    assert "BuiltinIPHost" in result.output


def test_dependencies_missing_standalone_download_is_soft(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """C7: a standalone dependency that 404s on download is skipped with a note; the rest succeed."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/needy",
        json=_collection_json([("acme", "app", "1.0.0")], _deps(schemas=[("acme", "gone")])),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/gone",
        json=_schema_detail("acme", "gone", deps=[]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/app/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/gone/download",
        status_code=404,
        json={"detail": "Schema not found"},
    )
    result = runner.invoke(app, ["get", "acme/needy", "-c", "--dependencies", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "dependency acme/gone could not be downloaded" in result.output
    assert "1 schemas downloaded" in result.output
    assert (tmp_path / "needy" / "app.yml").exists()
    assert not (tmp_path / "gone.yml").exists()


def test_dependencies_missing_prerequisite_member_fails_strictly(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """A prerequisite collection that lists a member with no published version is a hard error."""
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/app-pack",
        json=_collection_json([("acme", "app", "1.0.0")], _deps(collections=[("acme", "base")])),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/collections/acme/base",
        json=_collection_json([("acme", "missing", "9.9.9")]),
    )
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/app/versions/1.0.0/download",
        text=SCHEMA_YAML,
    )
    # The prerequisite collection's member cannot be fetched at its pinned version.
    httpx_mock.add_response(
        method="GET",
        url="https://marketplace.infrahub.app/api/v1/schemas/acme/missing/versions/9.9.9/download",
        status_code=404,
        json={"detail": "Version not found"},
    )
    result = runner.invoke(app, ["get", "acme/app-pack", "-c", "--dependencies", "-o", str(tmp_path)])

    assert result.exit_code == 1
    assert "acme/missing" in result.output


def test_dependencies_on_schema_is_noop_with_note(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """C3 / US3: --dependencies on a single schema downloads it normally with an informational note."""
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
    result = runner.invoke(app, ["get", "acme/network-base", "--dependencies", "-o", str(tmp_path)])

    assert result.exit_code == 0
    assert "--dependencies applies only to collections" in result.output
    assert "Downloaded schema acme/network-base v1.2.0" in result.output
    assert (tmp_path / "network-base.yml").exists()
