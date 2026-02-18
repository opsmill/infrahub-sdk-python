from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

from infrahub_sdk.ctl.schema import app
from tests.helpers.cli import remove_ansi_color

runner = CliRunner()

# ---------------------------------------------------------------------------
# Minimal schema API response builders
# ---------------------------------------------------------------------------

_BASE_NODE = {
    "id": None,
    "state": "present",
    "hash": None,
    "hierarchy": None,
    "label": None,
    "description": None,
    "include_in_menu": None,
    "menu_placement": None,
    "display_label": None,
    "display_labels": None,
    "human_friendly_id": None,
    "icon": None,
    "uniqueness_constraints": None,
    "documentation": None,
    "order_by": None,
    "inherit_from": [],
    "branch": "aware",
    "default_filter": None,
    "generate_profile": None,
    "generate_template": None,
    "parent": None,
    "children": None,
    "attributes": [],
    "relationships": [],
}

_BASE_GENERIC = {
    "id": None,
    "state": "present",
    "hash": None,
    "used_by": [],
    "label": None,
    "description": None,
    "include_in_menu": None,
    "menu_placement": None,
    "display_label": None,
    "display_labels": None,
    "human_friendly_id": None,
    "icon": None,
    "uniqueness_constraints": None,
    "documentation": None,
    "order_by": None,
    "attributes": [],
    "relationships": [],
}


def _make_rel(name: str, peer: str, **kwargs: object) -> dict:
    """Build a minimal RelationshipSchemaAPI-compatible dict."""
    rel: dict = {
        "id": None,
        "state": "present",
        "name": name,
        "peer": peer,
        "kind": "Generic",
        "label": None,
        "description": None,
        "identifier": None,
        "min_count": 0,
        "max_count": 0,
        "direction": "bidirectional",
        "on_delete": "no-action",
        "cardinality": "many",
        "branch": "aware",
        "optional": True,
        "order_weight": None,
        "inherited": False,
        "read_only": False,
        "hierarchical": None,
        "allow_override": "any",
    }
    rel.update(kwargs)
    return rel


def _make_node(namespace: str, name: str, **kwargs: object) -> dict:
    node = {**_BASE_NODE, "namespace": namespace, "name": name}
    node.update(kwargs)
    return node


def _make_generic(namespace: str, name: str, **kwargs: object) -> dict:
    generic = {**_BASE_GENERIC, "namespace": namespace, "name": name}
    generic.update(kwargs)
    return generic


def _make_profile(namespace: str, name: str) -> dict:
    return {
        "id": None,
        "state": "present",
        "namespace": namespace,
        "name": name,
        "label": None,
        "description": None,
        "include_in_menu": None,
        "menu_placement": None,
        "display_label": None,
        "display_labels": None,
        "human_friendly_id": None,
        "icon": None,
        "uniqueness_constraints": None,
        "documentation": None,
        "order_by": None,
        "inherit_from": [],
        "attributes": [],
        "relationships": [],
    }


def _schema_response(
    nodes: list[dict] | None = None,
    generics: list[dict] | None = None,
    profiles: list[dict] | None = None,
    templates: list[dict] | None = None,
) -> dict:
    return {
        "main": "aabbccdd",
        "nodes": nodes or [],
        "generics": generics or [],
        "profiles": profiles or [],
        "templates": templates or [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_schema_export_basic(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Two user namespaces produce two YAML files with correct content."""
    response = _schema_response(
        nodes=[
            _make_node("Infra", "Device"),
            _make_node("Dcim", "Rack"),
        ]
    )
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=response,
    )

    output_dir = tmp_path / "export"
    result = runner.invoke(app=app, args=["export", "--directory", str(output_dir)])

    assert result.exit_code == 0, result.stdout
    clean = remove_ansi_color(result.stdout)
    assert "Exported namespace 'Dcim'" in clean
    assert "Exported namespace 'Infra'" in clean

    dcim_file = output_dir / "dcim.yml"
    infra_file = output_dir / "infra.yml"
    assert dcim_file.exists()
    assert infra_file.exists()

    dcim_data = yaml.safe_load(dcim_file.read_text())
    infra_data = yaml.safe_load(infra_file.read_text())

    assert dcim_data["version"] == "1.0"
    assert any(n["name"] == "Rack" for n in dcim_data["nodes"])

    assert infra_data["version"] == "1.0"
    assert any(n["name"] == "Device" for n in infra_data["nodes"])


def test_schema_export_excludes_restricted_namespaces(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Restricted namespaces (Core, Builtin, Internal, etc.) are excluded from export."""
    response = _schema_response(
        nodes=[
            _make_node("Core", "MenuItem"),
            _make_node("Builtin", "Tag"),
            _make_node("Internal", "Node"),
        ]
    )
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=response,
    )

    output_dir = tmp_path / "export"
    result = runner.invoke(app=app, args=["export", "--directory", str(output_dir)])

    assert result.exit_code == 0, result.stdout
    assert "No user-defined schema found" in remove_ansi_color(result.stdout)
    assert not output_dir.exists()


def test_schema_export_excludes_profiles_templates(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """ProfileSchemaAPI and TemplateSchemaAPI objects are skipped."""
    profile = _make_profile("Infra", "ProfileDevice")
    template = {**profile, "name": "TemplateDevice"}
    response = _schema_response(profiles=[profile], templates=[template])
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=response,
    )

    output_dir = tmp_path / "export"
    result = runner.invoke(app=app, args=["export", "--directory", str(output_dir)])

    assert result.exit_code == 0, result.stdout
    assert "No user-defined schema found" in remove_ansi_color(result.stdout)
    assert not output_dir.exists()


def test_schema_export_namespace_filter(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """--namespace flag limits export to the specified namespace."""
    response = _schema_response(
        nodes=[
            _make_node("Infra", "Device"),
            _make_node("Dcim", "Rack"),
        ]
    )
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=response,
    )

    output_dir = tmp_path / "export"
    result = runner.invoke(app=app, args=["export", "--directory", str(output_dir), "--namespace", "Infra"])

    assert result.exit_code == 0, result.stdout
    assert (output_dir / "infra.yml").exists()
    assert not (output_dir / "dcim.yml").exists()


def test_schema_export_no_user_schema(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """No output files when all schemas are in restricted namespaces."""
    response = _schema_response(
        nodes=[
            _make_node("Core", "Repository"),
            _make_node("Builtin", "Tag"),
            _make_node("Internal", "Node"),
        ]
    )
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=response,
    )

    output_dir = tmp_path / "export"
    result = runner.invoke(app=app, args=["export", "--directory", str(output_dir)])

    assert result.exit_code == 0, result.stdout
    assert "No user-defined schema found" in remove_ansi_color(result.stdout)
    assert not output_dir.exists()


def test_schema_export_custom_directory(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Files are created in the directory specified via --directory."""
    response = _schema_response(nodes=[_make_node("Network", "Prefix")])
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=response,
    )

    custom_dir = tmp_path / "my-custom-export"
    result = runner.invoke(app=app, args=["export", "--directory", str(custom_dir)])

    assert result.exit_code == 0, result.stdout
    assert (custom_dir / "network.yml").exists()
    clean = remove_ansi_color(result.stdout)
    assert "Schema exported to" in clean
    assert custom_dir.name in clean


def test_schema_export_includes_generics(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Generic schemas are exported under the 'generics' key."""
    response = _schema_response(
        generics=[_make_generic("Infra", "GenericInterface")],
        nodes=[_make_node("Infra", "Device")],
    )
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=response,
    )

    output_dir = tmp_path / "export"
    result = runner.invoke(app=app, args=["export", "--directory", str(output_dir)])

    assert result.exit_code == 0, result.stdout
    infra_file = output_dir / "infra.yml"
    assert infra_file.exists()

    data = yaml.safe_load(infra_file.read_text())
    assert any(g["name"] == "GenericInterface" for g in data["generics"])
    assert any(n["name"] == "Device" for n in data["nodes"])


def test_schema_export_output_quality(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Relationships strip defaults; attrs/rels appear after scalar fields."""
    node = _make_node(
        "Infra",
        "Device",
        relationships=[
            # default-value rel — all strippable fields
            _make_rel("tags", "BuiltinTag"),
            # non-default rel — cardinality one, optional false, min/max_count 1
            _make_rel("site", "LocationSite", cardinality="one", optional=False, min_count=1, max_count=1),
        ],
    )
    response = _schema_response(nodes=[node])
    httpx_mock.add_response(
        method="GET",
        url="http://mock/api/schema?branch=main",
        json=response,
    )

    output_dir = tmp_path / "export"
    result = runner.invoke(app=app, args=["export", "--directory", str(output_dir)])
    assert result.exit_code == 0, result.stdout

    data = yaml.safe_load((output_dir / "infra.yml").read_text())
    node_data = data["nodes"][0]

    # --- field ordering: relationships must be last ---
    keys = list(node_data.keys())
    assert keys.index("name") < keys.index("relationships")

    tags_rel = next(r for r in node_data["relationships"] if r["name"] == "tags")
    site_rel = next(r for r in node_data["relationships"] if r["name"] == "site")

    # default values stripped from 'tags' rel
    for stripped_key in ("direction", "on_delete", "cardinality", "optional", "min_count", "max_count", "branch"):
        assert stripped_key not in tags_rel, f"'{stripped_key}' should have been stripped"

    # non-default values kept in 'site' rel
    assert site_rel["cardinality"] == "one"
    assert site_rel["optional"] is False
    assert site_rel["min_count"] == 1
    assert site_rel["max_count"] == 1
    # default direction/on_delete still stripped even on non-default rel
    assert "direction" not in site_rel
    assert "on_delete" not in site_rel
    assert "branch" not in site_rel
